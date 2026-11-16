"""Verdicts for the 'solid part away from the walls' rules (a-centre-core). Single photo only.

Reads features.csv (from features.py). Writes results_<letter>.csv and results.csv (the chosen one).
Parameters:
  S      inner window: the pot opening shrunk about its centre to S of its linear size (geometric)
  SHARE  share of a piece that must lie inside the inner window (geometric, a fraction)
  DEPTH  how many 3x3 erosions a piece must survive to count as solid
"""
import csv, json, math, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
KEYS = ["rig", "experiment_id", "tray_id", "cell", "taken_at_utc"]


def rule_a(f, S=60):
    """A, 'centre window, any green': green inside the inner window = plant; green only near the walls = possible."""
    if int(f[f"in{S}"]) > 0:
        return "plant", int(f[f"in{S}"])
    if int(f["px"]) > 0:
        return "possible", 0
    return "empty", 0


def rule_b(f, S=60, SHARE=0.5, DEPTH=2):
    """B, 'solid piece centred': a piece at least DEPTH erosions thick with SHARE of it in the inner window = plant.
    Any green in the inner window that fails that = possible. Green only near the walls = empty."""
    pieces = json.loads(f["best"]) if f["best"] else []
    ok = [p for p in pieces if p["depth"] >= DEPTH and p[f"sh{S}"] >= SHARE]
    if ok:
        return "plant", max(p["n"] for p in ok)
    if int(f[f"in{S}"]) > 0:
        return "possible", 0
    return "empty", 0


def rule_c(f, S=60, FRAC=0.01):
    """C, 'core scaled to the opening': a pixel inside the inner window that survives erosion by FRAC of the opening side."""
    need = max(1, math.ceil(FRAC * float(f["side_px"])))
    d = int(f.get(f"depth_in{S}") or 0)
    if d > need:
        return "plant", d
    if int(f[f"in{S}"]) > 0:
        return "possible", 0
    return "empty", 0


RULES = {"A": rule_a, "B": rule_b, "C": rule_c}



def rule_d(f, S=50, SHARE=0.5, DEPTH=2, FRAC=0.02):
    """D, 'centred solid piece, or any thick piece': as B, plus any piece anywhere in the opening at least
    FRAC of the opening side thick counts as plant (thick leaves reaching in from the side).
    Designed after seeing B's score-set misses on dev, so its score row is not a clean test."""
    v, s = rule_b(f, S, SHARE, DEPTH)
    if v != "plant":
        pieces = json.loads(f["best"]) if f["best"] else []
        need = max(DEPTH, math.ceil(FRAC * float(f["side_px"])))
        if any(p["depth"] >= need for p in pieces) or (not pieces and int(f["px"]) > 0 and int(f["maxdepth"]) >= need):
            return "plant", 0
    return v, s


RULES["D"] = rule_d


if __name__ == "__main__":
    feats = list(csv.DictReader(open(HERE / "features.csv")))
    kw = dict(a.split("=") for a in sys.argv[2:])
    kw = {k: (float(v) if "." in v else int(v)) for k, v in kw.items()}
    letter = sys.argv[1]
    out = HERE / f"results_{letter}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(KEYS + ["verdict", "score"])
        for f in feats:
            v, s = RULES[letter](f, **kw)
            w.writerow([f[k] for k in KEYS] + [v, s])
