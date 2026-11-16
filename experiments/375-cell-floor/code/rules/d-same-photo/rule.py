"""d-same-photo rules: compare a pot with the other pots in the same photo.

Uses features.csv (features.py). Per crop and region, "peak" = the highest 0.5 mm box-smoothed
green score (ExG, see STAT). core = the pot's centre (d < 0.6 of the half side), wall = the band
inside the opening against the wall (0.8 <= d < 1.0). Each photo (or tray in a photo) gets a
fringe level from its own pots, by robust statistics; no mm2 or pixel counts.

  python3 rule.py VARIANT OUT.csv [Q KP KQ STAT]

  F = the Q-th percentile of the reference peaks, S = 1.4826 * MAD of the reference peaks.
  plant if core_peak > F + KP * S; possible if core_peak > F + KQ * S; else empty.

Variants (reference):
  A  photo-walls: wall peaks of every cell in the photo.
  B  tray-walls:  wall peaks of the cells of the same tray in the photo.
  D  photo-walls plus filled centre: as E, and also "plant" when at least half of the pot's
     centre is in the plant mask (geometric: fringe lives at the wall and cannot fill the
     centre). For photos where every wall band is covered by leaves (no fringe reference).
  E  photo walls, lower-half spread: as A, but S = (P50 - P25) / 0.6745 of the wall peaks, so
     leaves lying over up to half of the wall bands do not widen the fringe spread.
  F  photo walls, lowest quarter: F = P25 of the wall peaks, S = (P25 - P5) / 0.97 (the normal
     spread implied by those two quantiles), so leaves over up to 3 of 4 wall bands do not
     move the fringe level.
  C  photo-cores: core peaks of every cell in the photo (the trap: when most pots hold
     plants the cores are no reference).
Each photo is judged alone: no earlier or later photos are used.
"""
import csv, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data"


def main():
    variant, out = sys.argv[1], sys.argv[2]
    Q = float(sys.argv[3]) if len(sys.argv) > 3 else 75
    KP = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
    KQ = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
    STAT = sys.argv[6] if len(sys.argv) > 6 else "upeak"
    feats = {r["key"]: r for r in csv.DictReader(open(HERE / "features.csv"))}
    rows = list(csv.DictReader(open(DATA / "index.csv")))
    groups = defaultdict(list)
    for r in rows:
        r["f"] = feats["|".join([r["rig"], r["experiment_id"], r["tray_id"], r["cell"], r["taken_at_utc"]])]
        g = (r["rig"], r["capture_id"]) + ((r["tray_id"],) if variant == "B" else ())
        groups[g].append(r)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rig", "experiment_id", "tray_id", "cell", "taken_at_utc", "verdict", "score"])
        for members in groups.values():
            ref = np.array([float(m["f"][("core_" if variant == "C" else "wall_") + STAT]) for m in members])
            med = np.median(ref)
            S = max(1.4826 * np.median(np.abs(ref - med)), 1e-3)
            if variant in ("E", "D"):  # lower-half spread: leaves over walls only push the upper half
                S = max((med - np.percentile(ref, 25)) / 0.6745, 1e-3)
            F = np.percentile(ref, Q)
            if variant == "F":  # clean lowest quarter: leaves may cover up to 3 of 4 wall bands
                F = np.percentile(ref, 25)
                S = max((F - np.percentile(ref, 5)) / (1.6449 - 0.6745), 1e-3)
            for m in members:
                z = (float(m["f"]["core_" + STAT]) - F) / S
                v = "plant" if z > KP else "possible" if z > KQ else "empty"
                if variant == "D" and int(m["f"]["core_mask"]) >= 0.5 * int(m["f"]["core_px"]):
                    v = "plant"
                w.writerow([m["rig"], m["experiment_id"], m["tray_id"], m["cell"], m["taken_at_utc"], v, round(z, 2)])


if __name__ == "__main__":
    main()
