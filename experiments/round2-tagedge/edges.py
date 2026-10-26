"""Edge methods on the green test squares (metrology log 18.9): each square found by the green
threshold, then its area read again by a half way edge in linear light, a partial area count and
GrabCut. Read only: rig.db is opened read-only and nothing under /var/lib/npec-rig/ is written.

    PYTHONPATH=src python experiments/round2-tagedge/edges.py OUT_DIR FROM_UTC TO_UTC

Writes OUT_DIR/edges.csv: one row per method, square and still, the same columns as methods.csv.
"""

import csv
import math
import sqlite3
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import load_manifest  # noqa: E402
from methods import exg  # noqa: E402
from squares import (  # noqa: E402
    DATA, DB, SQUARES, STEADY_EXPOSURE_US, match_squares, sheet_scale, squares_in, stills, stored_tags,
    tray_outlines,
)

MARGIN_PX = 30  # box around the square
INNER_PX = 8  # mask shrunk by this for the square's level
RING_PX = (20, 30)  # background ring, px outside the mask
NEAR_PX = 15  # partial area: pixels within this of the mask; GrabCut: probable background
METHODS = ["exg", "half_way", "partial_area", "grabcut"]


def linear_green(rgb):
    """2G - R - B in linear light, from 8-bit sRGB."""
    c = rgb.astype(np.float32) / 255
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 2 * lin[:, :, 1] - lin[:, :, 0] - lin[:, :, 2]


def _disc(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def edge_areas(rgb_box, mask_box):
    """Pixel counts of the square in a box by each edge method, from its exg mask in that box."""
    mask = mask_box.astype(np.uint8)
    inner = cv2.erode(mask, _disc(INNER_PX)).astype(bool)
    ring = cv2.dilate(mask, _disc(RING_PX[1])).astype(bool) & ~cv2.dilate(mask, _disc(RING_PX[0])).astype(bool)
    near = cv2.dilate(mask, _disc(NEAR_PX)).astype(bool)
    green = linear_green(rgb_box)
    square, background = float(np.median(green[inner])), float(np.median(green[ring]))
    half = green > (square + background) / 2
    n, labels = cv2.connectedComponents(half.astype(np.uint8), connectivity=8)
    ys, xs = np.nonzero(inner)
    centre_label = labels[int(np.median(ys)), int(np.median(xs))]
    half_px = int((labels == centre_label).sum()) if centre_label else 0
    fraction = np.clip((green - background) / (square - background), 0, 1)
    partial_px = float(fraction[near].sum())
    gc = np.full(mask.shape, cv2.GC_BGD, np.uint8)
    gc[near] = cv2.GC_PR_BGD
    gc[mask.astype(bool)] = cv2.GC_PR_FGD
    gc[inner] = cv2.GC_FGD
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(rgb_box, cv2.COLOR_RGB2BGR), gc, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
    grab_px = int(np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).sum())
    return {"exg": int(mask.sum()), "half_way": half_px, "partial_area": partial_px, "grabcut": grab_px}


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
            mask = exg(crop)
            n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
            for found in match_squares(squares_in(crop, (x0, y0), scale, exg), tray, tag, scale):
                cx, cy = found["x_px"] - x0, found["y_px"] - y0
                k = min(range(1, n), key=lambda i: math.dist(centroids[i], (cx, cy)))
                bx, by, bw, bh, _ = stats[k]
                bx0, by0 = max(bx - MARGIN_PX, 0), max(by - MARGIN_PX, 0)
                bx1, by1 = min(bx + bw + MARGIN_PX, crop.shape[1]), min(by + bh + MARGIN_PX, crop.shape[0])
                box_mask = labels[by0:by1, bx0:bx1] == k
                areas = edge_areas(crop[by0:by1, bx0:bx1], box_mask)
                sx, sy = SQUARES[found["square"]][:2]
                calliper, perimeter = sx * sy, 2 * (sx + sy)
                for method in METHODS:
                    area = areas[method] / scale**2
                    rows.append({
                        "method": method, "capture": path, "square": found["square"], "tray": tray,
                        "cell": found["cell"], "scale_px_per_mm": found["scale_px_per_mm"],
                        "pixels": round(areas[method], 1), "area_mm2": round(area, 2),
                        "calliper_mm2": round(calliper, 2), "error_pct": round(100 * (area / calliper - 1), 3),
                        "edge_width_mm": round((area - calliper) / perimeter, 4), "exposure_us": exposure,
                    })
        print(f"{path}: {sum(r['capture'] == path for r in rows)} rows", file=sys.stderr, flush=True)
    with open(out / "edges.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main(*sys.argv[1:4])
