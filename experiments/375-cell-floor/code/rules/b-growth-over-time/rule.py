"""#375 rule family "stays and grows": judge a cell by its own series of photos.

Input: features.npz from extract.py (each crop's mask mapped into the pot's own unit square,
a 32 x 32 grid of mask pixel counts) and data/index.csv.

A cell series is (rig, tray, cell); dev experiments 2 and 3 are joined (same pots and plants).
Photos are counted, not hours.

Variants (each writes results_<letter>.csv):
  A  "recurring in place" (causal): green now that overlaps green seen in at least K of the
     previous N photos -> plant; green now that is not yet confirmed -> possible; no green -> empty.
     A confirmed cell stays plant through up to R photos in a row with no green.
  B  "recurring and growing" (causal): as A, but plant also needs the area to have grown: the
     median area of the last 3 green photos is above the median of the first 3 green photos of
     the cell (each as a share of the pot opening). Recurring but not growing -> possible.
  C  "recurring, hindsight": A judged with the whole series (earlier and later photos): green now
     that overlaps green in at least K other photos within N photos either side -> plant.
  D  "recurring and growing, hindsight": the series grows (median area of its last 3 green
     photos above its first 3) and the green recurs in place (C) -> plant; recurring only -> possible.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent.parent / "data"

N = 6        # window, in photos
K = 2        # earlier sightings in the window that the current green must overlap
R = 5        # photos in a row with no green before a confirmed cell drops back
DIL = 1      # overlap tolerance, in grid bins (1/32 of the opening side)


def dilate(b, d=DIL):
    out = b.copy()
    for dy in range(-d, d + 1):
        for dx in range(-d, d + 1):
            out |= np.roll(np.roll(b, dy, 0), dx, 1) & _valid(dy, dx, b.shape)
    return out


def _valid(dy, dx, shape):
    m = np.ones(shape, bool)
    if dy > 0: m[:dy] = False
    if dy < 0: m[dy:] = False
    if dx > 0: m[:, :dx] = False
    if dx < 0: m[:, dx:] = False
    return m


def growing(areas):
    green = [a for a in areas if a > 0]
    if len(green) < 4:
        return False
    k = min(3, len(green) // 2)
    return np.median(green[-k:]) > np.median(green[:k])


W = 10       # photos over which the area trend is judged (E, F)
RHO = 0.5    # rank correlation of area with photo order that counts as rising (E, F)


def rising(areas):
    """Spearman rank correlation of area with photo order over the last W photos (zeros kept)."""
    a = np.asarray(areas[-W:], float)
    if len(a) < 4 or a.max() == 0:
        return False
    ra = _ranks(a)
    rt = np.arange(len(a), dtype=float)
    if ra.std() == 0:
        return False
    return np.corrcoef(ra, rt)[0, 1] >= RHO


def _ranks(a):
    order = np.argsort(a, kind="mergesort")
    r = np.empty(len(a))
    r[order] = np.arange(len(a))
    for v in np.unique(a):  # average ranks for ties (many zeros)
        m = a == v
        r[m] = r[m].mean()
    return r


def main():
    rows = list(csv.DictReader(open(DATA / "index.csv")))
    grids = np.load(HERE / "features.npz")["grids"]
    series = defaultdict(list)
    for i, r in enumerate(rows):
        series[(r["rig"], r["tray_id"], r["cell"])].append(i)
    out = {v: [None] * len(rows) for v in "ABCDEF"}
    for key, ii in series.items():
        ii.sort(key=lambda i: rows[i]["taken_at_utc"])
        occ = [grids[i] > 0 for i in ii]
        dil = [dilate(o) for o in occ]
        area = [grids[i].sum() / float(rows[i]["opening_px"]) for i in ii]
        n = len(ii)

        def hits(t, lo, hi):
            if not occ[t].any():
                return 0
            return sum(1 for s in range(lo, hi) if s != t and (occ[t] & dil[s]).any())

        # causal A and B
        confirmed_a = confirmed_b = confirmed_e = False
        dry = 0
        for t in range(n):
            h = hits(t, max(0, t - N), t)
            green = occ[t].any()
            dry = 0 if green else dry + 1
            if dry >= R:
                confirmed_a = confirmed_b = confirmed_e = False
            if green and h >= K:
                confirmed_a = True
                if growing(area[: t + 1]):
                    confirmed_b = True
                if rising(area[: t + 1]):
                    confirmed_e = True
            va = "plant" if confirmed_a else ("possible" if green else "empty")
            vb = "plant" if confirmed_b else ("possible" if (green or confirmed_a) else "empty")
            out["A"][ii[t]] = (va, h)
            out["B"][ii[t]] = (vb, h)
            ve = "plant" if confirmed_e else ("possible" if (green or confirmed_a) else "empty")
            out["E"][ii[t]] = (ve, h)
        # hindsight C and D
        grows_all = growing(area)
        rises_any = any(rising(area[: e]) for e in range(4, n + 1))
        rec = [hits(t, max(0, t - N), min(n, t + N + 1)) >= K for t in range(n)]
        first = next((t for t in range(n) if rec[t]), None)
        dry = 0
        for t in range(n):
            h = hits(t, max(0, t - N), min(n, t + N + 1))
            green = occ[t].any()
            # a cell with recurring green is a plant from its first recurring sighting on,
            # unless R photos in a row show no green at all
            dry = 0 if green else dry + 1
            confirmed = first is not None and t >= first and dry < R
            vc = "plant" if confirmed else ("possible" if green else "empty")
            vd = "plant" if (confirmed and grows_all) else (
                "possible" if (green or confirmed) else "empty")
            out["C"][ii[t]] = (vc, h)
            out["D"][ii[t]] = (vd, h)
            # F: hindsight E; the series rose somewhere: any window of W photos with rising area
            vf = "plant" if (confirmed and rises_any) else (
                "possible" if (green or confirmed) else "empty")
            out["F"][ii[t]] = (vf, h)
    for v, res in out.items():
        with open(HERE / f"results_{v}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rig", "experiment_id", "tray_id", "cell", "taken_at_utc", "verdict", "score"])
            for r, (verdict, score) in zip(rows, res):
                w.writerow([r["rig"], r["experiment_id"], r["tray_id"], r["cell"],
                            r["taken_at_utc"], verdict, score])


if __name__ == "__main__":
    main()
