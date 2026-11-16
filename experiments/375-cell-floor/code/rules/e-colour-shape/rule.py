"""Verdict per crop from per-piece colour and shape (e-colour-shape, #375).

Usage: python rule.py VARIANT   (A, B or C) -> results_<VARIANT>.csv
Uses only the photo itself (no earlier photos): not causal-history dependent at all.
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
KEYS = ["rig", "experiment_id", "tray_id", "cell", "taken_at_utc"]

# Geometric: the wall band is the outer EDGE_BAND of the opening side (fraction of the side).
EDGE_BAND = 0.04
# Shape: a piece is "long and thin" when its long axis is at least ELONG times its short axis.
ELONG = 2.5
# Colour: the piece's ring (3 px round it) counts as "next to blue plastic" above RING_BLUE.
RING_BLUE = 0.25
# Colour contrast, adaptive: piece ExG above the soil median by Z_LEAF MADs of the soil.
Z_LEAF = 8.0


def f(p, k):
    return float(p[k])


def is_fringe_A(p):
    """A, wall-hugging thin piece: touches the wall band AND (long and thin OR beside blue)."""
    return f(p, "edge_min") < EDGE_BAND and (f(p, "elong") >= ELONG or f(p, "ring_blue") >= RING_BLUE)


def is_leaf_B(p):
    """B, contrast to soil: a leaf is clearly greener than its own soil and not next to blue
    plastic, or it lies away from the wall band (then colour alone decides)."""
    if f(p, "exg_z") < Z_LEAF:
        return False
    if f(p, "edge_min") < EDGE_BAND and f(p, "ring_blue") >= RING_BLUE:
        return False
    return True


def bluish(p):
    """The piece's blue is at least as strong as its green: tray plastic tint, not a leaf.
    B/G = 1 is a physical boundary (equal channels), not a tuned number."""
    return f(p, "b_over_g") >= 1.0


def wall_sliver(p):
    """Long and thin and inside the wall band of the opening (geometric band)."""
    return f(p, "edge_min") < EDGE_BAND and f(p, "elong") >= ELONG


def verdict(pieces, variant):
    if variant == "A":    # blue tint only
        leaves = [p for p in pieces if not bluish(p)]
        return ("plant" if leaves else "empty"), sum(f(p, "area_frac") for p in leaves)
    if variant == "B":    # blue tint + wall sliver; leaves only in the wall band -> possible
        leaves = [p for p in pieces if not bluish(p) and not wall_sliver(p)]
        s = sum(f(p, "area_frac") for p in leaves)
        if not leaves:
            return "empty", 0.0
        if any(f(p, "edge_min") >= EDGE_BAND for p in leaves):
            return "plant", s
        return "possible", s
    if variant == "C":    # wall-hugging shape only, no colour (for comparison)
        leaves = [p for p in pieces if not is_fringe_A(p)]
        return ("plant" if leaves else "empty"), sum(f(p, "area_frac") for p in leaves)
    raise SystemExit("variant A, B or C")


def main():
    variant = sys.argv[1]
    pieces = defaultdict(list)
    for p in csv.DictReader(open(HERE / "pieces.csv")):
        pieces[tuple(p[k] for k in KEYS)].append(p)
    out = open(HERE / f"results_{variant}.csv", "w", newline="")
    w = csv.writer(out)
    w.writerow(KEYS + ["verdict", "score"])
    for r in csv.DictReader(open(ROOT / "data/index.csv")):
        k = tuple(r[c] for c in KEYS)
        v, s = verdict(pieces.get(k, []), variant)
        w.writerow(list(k) + [v, round(s, 6)])
    out.close()


if __name__ == "__main__":
    main()
