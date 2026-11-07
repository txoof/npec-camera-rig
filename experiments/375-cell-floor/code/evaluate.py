"""Score a rule's verdicts for #375 the same way for every rule.

Usage: python3 evaluate.py RESULTS.csv [--set tune|score|all]

RESULTS.csv columns: rig, experiment_id, tray_id, cell, taken_at_utc, verdict (empty, possible,
plant), score (optional). One row per crop in data/index.csv. Labels come from data/labels.csv
(made by eye from the RGB crops, not from any rule).

Sets: tune = production trays 1 to 6; score = production trays 7 to 12 plus development.
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"


def which_set(rig, tray):
    if rig == "prod":
        return "tune" if int(tray) <= 6 else "score"
    return "score"


def key(r):
    return (r["rig"], str(r["experiment_id"]), str(r["tray_id"]), r["cell"], r["taken_at_utc"])


def main():
    path = sys.argv[1]
    want = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "score"
    index = {key(r): r for r in csv.DictReader(open(DATA / "index.csv"))}
    results = {key(r): r for r in csv.DictReader(open(path))}
    missing = [k for k in index if k not in results]
    groups = defaultdict(lambda: defaultdict(int))
    for k, row in index.items():
        if want != "all" and which_set(row["rig"], row["tray_id"]) != want:
            continue
        verdict = results.get(k, {}).get("verdict", "none")
        if row["label_outcome"] == "empty":
            g = f"{row['rig']} empty: {row['label_contents']}"
        elif row["label_outcome"] == "plant" and row["label_visible_plant"] == "True":
            d = int(row["day_since_grow_start"])
            span = "days 0-2" if d <= 2 else "days 3-6" if d <= 6 else "days 7-13" if d <= 13 else "days 14+ (blue mats)"
            g = f"{row['rig']} seedling visible, {span}"
        else:
            g = f"{row['rig']} plant not yet visible"
        groups[g][verdict] += 1
        groups[g]["n"] += 1
    out = {}
    for g in sorted(groups):
        c = groups[g]
        n = c["n"]
        out[g] = {"n": n, **{v: round(100 * c[v] / n, 1) for v in ("plant", "possible", "empty", "none")}}
    print(json.dumps({"set": want, "missing_rows": len(missing), "percent_by_group": out}, indent=1))


if __name__ == "__main__":
    main()
