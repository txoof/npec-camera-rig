"""Charts for metrology log 18 from measure.py's sheets.csv.

    python experiments/round2-tagedge/chart.py OUT_DIR/sheets.csv OUT.png
"""

import csv
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import svgchart  # noqa: E402

KINDS = [  # fixed order: colour and marker per kind
    ("calibration", "Calibration photo"),
    ("validation", "Validation photo"),
    ("calibration (old folder)", "Calibration photo, before #103"),
    ("experiment still (17.6)", "Experiment 18 still, 23 Oct (17.6)"),
]
SLOTS = [f"{row} {n}" for row in ("North", "South") for n in range(1, 7)]
CURRENT = ("calibration", "validation", "experiment still (17.6)")


def num(value):
    return float(value) if value not in ("", None) else None


def when(photo):
    tail = photo.split("/")[-2:] if "/" in photo else None
    if tail:
        return datetime.strptime("/".join(tail), "%Y-%m-%d/%H%M%S_%f")
    return datetime.strptime(photo, "%Y%m%dT%H%M%S%f")


def main(path, out):
    rows = list(csv.DictReader(open(path)))
    by_photo = defaultdict(list)
    for r in rows:
        by_photo[r["photo"]].append(r)
    photo_median = {p: statistics.median(num(r["ratio_median"]) for r in rs) for p, rs in by_photo.items()}
    start = min(when(p) for p in by_photo)
    ref = [(1.0, "1 = no bias")]

    def series(points_for, kinds=KINDS):
        out = []
        for i, (kind, label) in enumerate(KINDS):
            if kind not in [k for k, _ in kinds]:
                continue
            pts = points_for(kind)
            if pts:
                out.append({"label": label, "points": pts, "colour": svgchart.SERIES[i], "marker": svgchart.MARKERS[i]})
        return out

    day = lambda p: (when(p) - start).total_seconds() / 86400  # noqa: E731
    first_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    ticks = []
    for offset in range(0, 40, 7):
        t = first_day.timestamp() + offset * 86400
        ticks.append(((t - start.timestamp()) / 86400, datetime.fromtimestamp(t).strftime("%d %b")))
    panels = [
        svgchart.panel(
            series(lambda k: [(day(p), m) for p, m in photo_median.items() if by_photo[p][0]["kind"] == k]),
            title="a. Each photo (median of its sheets), by date", xlabel="date", ylabel="edge scale / spacing scale",
            hlines=ref, xticks=[t for t in ticks if t[0] <= max(day(p) for p in by_photo) + 1],
        ),
        svgchart.panel(
            series(lambda k: [(num(by_photo[p][0]["exposure_us"]), m) for p, m in photo_median.items()
                              if by_photo[p][0]["kind"] == k and by_photo[p][0]["exposure_us"]],
                   [x for x in KINDS if x[0] in CURRENT]),
            title="b. Each photo, by exposure time (photos since 8 Oct)", xlabel="exposure time (µs)",
            ylabel="edge scale / spacing scale", hlines=ref,
        ),
    ]
    # c. by slot: each sheet of the photos since 8 October, offset from its photo's median.
    slot_pts = []
    for r in rows:
        if r["kind"] in CURRENT and r["slot"] in SLOTS:
            slot_pts.append((SLOTS.index(r["slot"]) + 1, num(r["ratio_median"]) - photo_median[r["photo"]]))
    medians = [(i + 1, statistics.median(y for x, y in slot_pts if x == i + 1)) for i in range(12) if any(x == i + 1 for x, _ in slot_pts)]
    panels.append(svgchart.panel(
        [{"label": "one sheet, against its photo's median", "points": slot_pts, "colour": "#9ec5f4", "marker": "circle"},
         {"label": "median of the slot", "points": medians, "colour": svgchart.SERIES[0], "marker": "diamond"}],
        title="c. By slot (photos since 8 Oct)", xlabel="slot (N = North, S = South, from west)",
        ylabel="difference from photo median", hlines=[(0.0, "")],
        xticks=[(i + 1, ("N" if s.startswith("N") else "S") + s[-1]) for i, s in enumerate(SLOTS)], xlim=(0.4, 12.6),
    ))
    dist_pts = [(num(r["from_centre_px"]), num(r["ratio_median"]) - photo_median[r["photo"]]) for r in rows if r["kind"] in CURRENT]
    panels.append(svgchart.panel(
        [{"label": "one sheet, against its photo's median", "points": dist_pts, "colour": svgchart.SERIES[0], "marker": "circle"}],
        title="d. By distance from the image centre (since 8 Oct)", xlabel="sheet centre from image centre (px)",
        ylabel="difference from photo median", hlines=[(0.0, "")],
    ))
    svgchart.to_png(panels, out, heading=f"Tag edges against tag spacing, metrology log 18: {len(rows)} sheets in {len(by_photo)} photos")


if __name__ == "__main__":
    main(*sys.argv[1:3])
