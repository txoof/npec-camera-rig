"""Summarise methods.py or edges.py runs (metrology log 18.8, 18.9): per method, background and
square size, how often the squares were found, the median error, the range over single stills and
the median edge width.

    python experiments/round2-tagedge/methods_summary.py OUT.csv LABEL=DIR [LABEL=DIR ...]

Each DIR holds a methods.csv or an edges.csv; LABEL names its background, e.g.
"black paper=OUT/methods-paper".
"""

import collections
import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from squares import SQUARES  # noqa: E402


def nominal(side_mm):
    return round(side_mm / 5) * 5


def main(out, *runs):
    per_size = collections.Counter(nominal(sx) for sx, *_ in SQUARES.values())
    errors, widths, stills = collections.defaultdict(list), collections.defaultdict(list), {}
    labels, methods = [], []
    for run in runs:
        label, folder = run.split("=", 1)
        labels.append(label)
        captures = set()
        table = next(Path(folder) / n for n in ("methods.csv", "edges.csv") if (Path(folder) / n).exists())
        for r in csv.DictReader(open(table)):
            if r["method"] not in methods:
                methods.append(r["method"])
            key = (r["method"], label, nominal(float(r["calliper_mm2"]) ** 0.5))
            errors[key].append(float(r["error_pct"]))
            widths[key].append(float(r["edge_width_mm"]))
            captures.add(r["capture"])
        stills[label] = len(captures)
    rows = []
    for method in methods:
        for label in labels:
            for size in sorted(per_size):
                e = errors.get((method, label, size), [])
                rows.append({
                    "method": method, "background": label, "size_mm": size, "stills": stills[label],
                    "found_pct": round(100 * len(e) / (stills[label] * per_size[size])),
                    "median_error_pct": round(statistics.median(e), 1) if e else "",
                    "min_error_pct": round(min(e), 1) if e else "",
                    "max_error_pct": round(max(e), 1) if e else "",
                    "median_edge_width_mm": round(statistics.median(widths[(method, label, size)]), 2) if e else "",
                })
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for r in rows:
        print(*r.values(), sep="\t")


if __name__ == "__main__":
    main(*sys.argv[1:])
