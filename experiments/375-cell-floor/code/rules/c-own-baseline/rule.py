"""Rule c-own-baseline (#375): green that is new relative to the cell's own wall fringe.

Works in pot coordinates (u, v in [0, 1] = the pot opening, from the opening polygon), on the
70 x 70 grid made by extract.py (a bin is 0.02 of the pot side). A bin is green when at least
GREEN_SHARE of its samples are in the ExG mask. d = distance from the pot wall as a share of
the pot side (0 at the wall, 0.5 at the centre). Only bins inside the opening (d > 0) count.

Variants (python3 rule.py VARIANT [CENTRE] [REPEAT]):
  A  own-fringe-map: band green that repeats in the cell's own earlier photos is fringe
  B  wall-band-only: no history; band green is "possible", centre green is "plant"
  C  own-map-everywhere: like A but the learned map may cover any bin, centre included
  AH own-fringe-map-hindsight: A, learning from all of the cell's photos except this one
Causal variants (A, B, C) use only photos taken before this one, of the same cell series.
"""
import csv, sys
import numpy as np
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = Path.home() / "scratch/375-cell-floor/data"
variant = sys.argv[1]
CENTRE = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25   # geometric: d of the centre zone
REPEAT = float(sys.argv[3]) if len(sys.argv) > 3 else 1 / 3  # share of earlier photos
GREEN_SHARE = 0.0
out = Path(sys.argv[4]) if len(sys.argv) > 4 else HERE / f"results_{variant}.csv"

z = np.load(HERE / "features.npz")
f = np.nan_to_num(z["frac"]); G = int(z["g"]); lo, hi = float(z["lo"]), float(z["hi"])
rows = list(csv.DictReader(open(D / "index.csv")))
t = (np.arange(G) + 0.5) / G * (hi - lo) + lo
U, V = np.meshgrid(t, t)
d = np.minimum.reduce([U, 1 - U, V, 1 - V])
inside = d > 0
centre = d >= CENTRE
band = inside & ~centre
green = (f > GREEN_SHARE) & inside

# cell series: dev experiments 2 and 3 are the same physical pots, so the series runs across them
series = defaultdict(list)
for i, r in enumerate(rows):
    series[(r["rig"], r["tray_id"], r["cell"])].append(i)

verdict = [None] * len(rows); score = [0.0] * len(rows)
for ix in series.values():
    ix.sort(key=lambda i: rows[i]["taken_at_utc"])
    for k, i in enumerate(ix):
        g = green[i]
        if variant == "AH":
            hist = [j for j in ix if j != i]
        elif variant in ("A", "C"):
            hist = ix[:k]
        else:
            hist = []
        if hist:
            p = green[hist].mean(0)
            base = p >= REPEAT
            if variant != "C":
                base &= band
        else:
            base = np.zeros_like(g)
        new = g & ~base
        nc = (new & centre).sum(); nb = (new & band).sum()
        score[i] = float(nc + 0.5 * nb)
        if nc > 0:
            verdict[i] = "plant"
        elif nb > 0:
            verdict[i] = "possible"
        else:
            verdict[i] = "empty"

with open(out, "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["rig", "experiment_id", "tray_id", "cell", "taken_at_utc", "verdict", "score"])
    for i, r in enumerate(rows):
        w.writerow([r["rig"], r["experiment_id"], r["tray_id"], r["cell"], r["taken_at_utc"], verdict[i], score[i]])
