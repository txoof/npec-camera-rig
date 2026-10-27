"""Four ways to pick out green pixels, tried on the same green test squares (#286, the literature
comment of 2026-10-26 14:03 UTC). Each still is decoded once and every method reads the same tray
crops, with the scale from the tag sheet on the tray as in squares.py. Read only: rig.db is opened
read-only and nothing under /var/lib/npec-rig/ is written.

    PYTHONPATH=src python experiments/round2-tagedge/methods.py OUT_DIR FROM_UTC TO_UTC

Writes OUT_DIR/methods.csv: one row per method, square and still.

Thresholds are the published ones, not tuned on these squares:
- exg: 2g - r - b above 0.1 and G > R, the rig's green threshold (Woebbecke et al., 1995).
- canopeo: 2G - R - B above 20 on 8-bit values, R/G and B/G below 0.95 (Patrignani and Ochsner,
  2015, rule as reimplemented).
- exg_exr: (2g - r - b) - (1.4r - g) above 0 (Meyer and Camargo Neto, 2008).
- exg_otsu: 2g - r - b above an Otsu threshold chosen per tray crop, and G > R.
"""

import csv
import sys
from pathlib import Path

import cv2
import numpy as np

from npec_rig.segmentation import ExGSegmenter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from squares import match_squares, squares_in, tray_crops  # noqa: E402


def _channels(rgb):
    r, g, b = (rgb[:, :, i].astype(np.float32) for i in range(3))
    return r, g, b


def _exg(r, g, b):
    return (2 * g - r - b) / (r + g + b + 1e-6)


def exg(rgb):
    return ExGSegmenter().segment(rgb)


def canopeo(rgb):
    r, g, b = _channels(rgb)
    return (2 * g - r - b > 20) & (r < 0.95 * g) & (b < 0.95 * g)


def exg_exr(rgb):
    r, g, b = _channels(rgb)
    s = r + g + b + 1e-6
    return _exg(r, g, b) - (1.4 * r - g) / s > 0


def exg_otsu(rgb):
    r, g, b = _channels(rgb)
    index = _exg(r, g, b)
    scaled = np.clip((index + 1) / 3 * 255, 0, 255).astype(np.uint8)
    level, _ = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return (scaled > level) & (g > r)


METHODS = {"exg": exg, "canopeo": canopeo, "exg_exr": exg_exr, "exg_otsu": exg_otsu}


def main(out, start, end):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for path, exposure, tray, tag, scale, _, crop, offset in tray_crops(start, end):
        for name, segment in METHODS.items():
            for row in match_squares(squares_in(crop, offset, scale, segment), tray, tag, scale):
                rows.append({"method": name, "capture": path, **row, "exposure_us": exposure})
    with open(out / "methods.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main(*sys.argv[1:4])
