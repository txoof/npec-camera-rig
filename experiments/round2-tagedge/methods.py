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
import sqlite3
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import load_manifest  # noqa: E402
from squares import (  # noqa: E402
    DATA, DB, SQUARES, STEADY_EXPOSURE_US, match_squares, sheet_scale, squares_in, stills, stored_tags,
    tray_outlines,
)


def _channels(rgb):
    r, g, b = (rgb[:, :, i].astype(np.float32) for i in range(3))
    return r, g, b


def _exg(r, g, b):
    return (2 * g - r - b) / (r + g + b + 1e-6)


def exg(rgb):
    r, g, b = _channels(rgb)
    return (_exg(r, g, b) > 0.1) & (g > r)


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
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    manifest = load_manifest()
    rows = []
    for capture_id, path, exposure, gain in stills(db, start, end):
        if exposure > STEADY_EXPOSURE_US or gain > 1.0:
            continue
        tags = stored_tags(db, path)
        outlines = tray_outlines(db, capture_id)
        bgr = cv2.imread(str(DATA / f"{path}.jpg"))
        sheet_scales = {tray: sheet_scale(tags, outline, manifest) for tray, outline in outlines.items()}
        pooled = statistics.median(s for s in sheet_scales.values() if s)
        for tray in sorted({v[2] for v in SQUARES.values()}):
            outline = outlines.get(tray)
            tag = next((t for t in tags if t.tag_id == tray), None)
            if not outline or tag is None:
                continue
            scale = sheet_scales.get(tray) or pooled
            xs, ys = zip(*outline)
            x0, y0 = max(int(min(xs)), 0), max(int(min(ys)), 0)
            x1, y1 = min(int(max(xs)) + 1, bgr.shape[1]), min(int(max(ys)) + 1, bgr.shape[0])
            crop = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
            for name, segment in METHODS.items():
                pieces = squares_in(crop, (x0, y0), scale, segment)
                for row in match_squares(pieces, tray, tag, scale):
                    rows.append({"method": name, "capture": path, **row, "exposure_us": exposure})
        print(f"{path}: {sum(r['capture'] == path for r in rows)} rows", file=sys.stderr, flush=True)
    with open(out / "methods.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main(*sys.argv[1:4])
