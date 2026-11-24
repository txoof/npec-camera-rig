"""Issue #483: how far apart are two outlines of one tray, and what does an outline shift cost?

    PYTHONPATH=src python experiments/483-outline-tolerance/run.py

(a) `find_outlines` run twice on each stored still (the quarter-size fixtures of
    tests/fixtures/trays/blue-finder/): the largest distance between a corner of one run and the
    nearest corner of the other. Expected 0 px.
(b) Each outline moved by 1, 2 and 5 px (full-size photo pixels, in x, then in y): the change in
    that tray's plant area by the fixed green cutoff (`measure_trays` on the quarter-size
    image's mask, enlarged 4 times), in mm2 and in per cent of the tray's area without a shift.

Writes nothing; prints the tables that go in docs/metrology-log.md, section 47.
"""

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from npec_rig import segmentation
from npec_rig.calibration import ScaleField
from npec_rig.tray_placement import find_outlines

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "trays" / "blue-finder"
SHIFTS_PX = (1, 2, 5)


def scale_field(d: dict) -> ScaleField:
    return ScaleField(tuple(d["coeffs"]), d["mean_px_per_mm"], d["residual_std_pct"])


def corner_gap(a, b) -> float:
    return max(max(min(math.dist(p, q) for q in b) for p in a), max(min(math.dist(p, q) for q in a) for p in b))


def main() -> None:
    expected = json.loads((FIXTURES / "expected.json").read_text())["fixtures"]
    print("(a) largest corner gap between two runs of find_outlines on one still, px")
    print("| still | trays | largest gap (px) |\n|---|---|---|")
    rows = []
    for name, fx in sorted(expected.items()):
        with Image.open(FIXTURES / f"{name}.jpg") as image:
            rgb = np.asarray(image.convert("RGB"))
        field = scale_field(fx["scale_field"])
        first = find_outlines(rgb, field, fx["factor"])
        second = find_outlines(rgb, field, fx["factor"])
        gaps = [corner_gap(a.corners, b.corners) for a, b in zip(first, second, strict=True)]
        print(f"| {name} | {len(first)} | {max(gaps, default=0.0):g} |")
        if first:
            rows.append((name, fx, rgb, field, first))

    print("\n(b) change in a tray's plant area when its outline moves, fixed green cutoff")
    print("| still | shift (px) | trays | mean change (mm2) | largest change (mm2) | largest change (% of unshifted area) |")
    print("|---|---|---|---|---|---|")
    for name, fx, rgb, field, outlines in rows:
        f = fx["factor"]
        mask = cv2.resize(segmentation.ExGSegmenter().segment(rgb).astype(np.uint8), None, fx=f, fy=f,
                          interpolation=cv2.INTER_NEAREST).astype(bool)
        base = segmentation.measure_trays(mask, [(o.corners, o.centre) for o in outlines], field)
        for s in SHIFTS_PX:
            changes, pct = [], []
            for dx, dy in ((s, 0), (0, s)):
                moved = [(tuple((x + dx, y + dy) for x, y in o.corners), (o.centre[0] + dx, o.centre[1] + dy)) for o in outlines]
                after = segmentation.measure_trays(mask, moved, field)
                for b, a in zip(base, after, strict=True):
                    d = abs((a.area_mm2 or 0.0) - (b.area_mm2 or 0.0))
                    changes.append(d)
                    if b.area_mm2:
                        pct.append(100 * d / b.area_mm2)
            print(f"| {name} | {s} | {len(outlines)} | {np.mean(changes):.1f} | {max(changes):.1f} | {max(pct, default=float('nan')):.2f} |")


if __name__ == "__main__":
    sys.exit(main())
