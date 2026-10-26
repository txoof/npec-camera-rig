"""The green test squares on the pots, metrology log 18.5: each square's area read by the green
threshold, with the scale taken from the tag spacing of the tag sheet on the same tray. Read only:
rig.db is opened read-only and nothing under /var/lib/npec-rig/ is written.

    PYTHONPATH=src python experiments/round2-tagedge/squares.py OUT_DIR FROM_UTC TO_UTC

FROM_UTC, TO_UTC: e.g. 2026-10-26T10:45 2026-10-26T12:15. Stills with an exposure above
STEADY_EXPOSURE_US or a gain above 1 (a lights ramp) are left out. Writes OUT_DIR/squares.csv
(one row per square and still) and prints a summary per square.
"""

import csv
import json
import math
import sqlite3
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

from npec_rig.segmentation import ExGSegmenter
from npec_rig.tags import TagDetection
from npec_rig.tray_placement import TRAY_SIZE_MM

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure import load_manifest, pair_ratios  # noqa: E402

DATA = Path("/var/lib/npec-rig")
DB = DATA / "rig.db"
STEADY_EXPOSURE_US = 6000
CELL_MM = 69.7  # cell centre to cell centre (reference/trays.md, derived)

# Aaron, 2026-10-26: calliper sides (mean of 3, mm) and where each square lies (tray, cell).
SQUARES = {
    "A": (9.953, 9.907, 9, "C1"), "B": (9.953, 9.943, 11, "C1"), "C": (9.947, 9.940, 12, "D1"),
    "D": (9.910, 9.983, 8, "C1"), "H": (19.950, 19.920, 11, "A2"), "E": (19.953, 19.933, 11, "A4"),
    "F": (20.007, 19.957, 12, "C1"), "G": (19.957, 19.983, 7, "D2"), "K": (40.007, 39.990, 9, "B1"),
    "L": (39.970, 39.930, 12, "A3"), "I": (54.957, 54.930, 9, "A3"), "J": (54.973, 54.993, 10, "D2"),
}


def cell_offset_mm(cell):
    """Distance from cell A1 to `cell`, in cells' pitch, mm."""
    return CELL_MM * math.hypot(ord(cell[0]) - ord("A"), int(cell[1:]) - 1)


def stills(db, start, end):
    return db.execute(
        "SELECT id, path, exposure_us, analogue_gain FROM capture WHERE taken_at >= ? AND taken_at < ? "
        "AND experiment_id IS NOT NULL ORDER BY taken_at",
        (start, end),
    ).fetchall()


def stored_tags(db, path):
    row = db.execute(
        "SELECT value FROM capture_analysis WHERE kind='tags' AND source=? ORDER BY version DESC LIMIT 1", (path,)
    ).fetchone()
    return [TagDetection(t["tag_id"], tuple(map(tuple, t["corners"])), tuple(t["centre"])) for t in json.loads(row[0])]


def tray_outlines(db, capture_id):
    """tray -> its outside outline in pixels, from the tray reading's centre and tilt and the tray's
    measured size (tray_placement.TRAY_SIZE_MM) at a rough 4.95 px/mm: only to crop and to find the
    tags lying on it."""
    rows = db.execute(
        "SELECT tray_id, centre_x_px, centre_y_px, tilt_deg FROM tray_reading WHERE capture_id = ?", (capture_id,)
    ).fetchall()
    out = {}
    for tray, cx, cy, tilt in rows:
        half_w, half_h = TRAY_SIZE_MM[0] / 2 * 4.95, TRAY_SIZE_MM[1] / 2 * 4.95
        t = math.radians(tilt)
        out[tray] = [
            (cx + u * math.cos(t) - v * math.sin(t), cy + u * math.sin(t) + v * math.cos(t))
            for u, v in ((-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h))
        ]
    return out


def inside(point, outline):
    return cv2.pointPolygonTest(np.array(outline, dtype=np.float32), point, False) >= 0


def sheet_scale(tags, outline, manifest):
    """Median tag spacing scale (px/mm) of the calibration tags inside `outline`, or None."""
    on_tray = [t for t in tags if 300 <= t.tag_id <= 449 and inside(t.centre, outline)]
    ratios = [r[4] for r in pair_ratios(on_tray, manifest)]
    return statistics.median(ratios) if ratios else None


def squares_in(rgb_crop, offset, scale):
    """Square green pieces in a crop: (pixels, centre x, centre y) in full-size pixels."""
    mask = ExGSegmenter().segment(rgb_crop).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    found = []
    for k in range(1, n):
        x, y, w, h, area = stats[k]
        side_mm = math.sqrt(area) / scale
        if not 6 <= side_mm <= 70 or not 0.8 <= w / h <= 1.25 or area / (w * h) < 0.85:
            continue
        found.append((int(area), centroids[k][0] + offset[0], centroids[k][1] + offset[1]))
    return found


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
        sheet_scales = {}
        for tray, outline in outlines.items():
            sheet_scales[tray] = sheet_scale(tags, outline, manifest)
        pooled = statistics.median(s for s in sheet_scales.values() if s)
        for tray in sorted({v[2] for v in SQUARES.values()}):
            outline = outlines.get(tray)
            tag = next((t for t in tags if t.tag_id == tray), None)
            if not outline or tag is None:
                continue
            scale = sheet_scales.get(tray)
            scale_from = "tag sheet on the tray" if scale else "median of the tag sheets in the photo"
            scale = scale or pooled
            xs, ys = zip(*outline)
            x0, y0 = max(int(min(xs)), 0), max(int(min(ys)), 0)
            x1, y1 = min(int(max(xs)) + 1, bgr.shape[1]), min(int(max(ys)) + 1, bgr.shape[0])
            crop = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
            pieces = squares_in(crop, (x0, y0), scale)
            for letter, (sx, sy, sq_tray, cell) in SQUARES.items():
                if sq_tray != tray:
                    continue
                want_px = sx * sy * scale**2
                want_from_tag = cell_offset_mm(cell) * scale
                candidates = [p for p in pieces if 0.6 <= p[0] / want_px <= 1.5]
                if not candidates:
                    continue
                piece = min(candidates, key=lambda p: abs(math.dist(p[1:], tag.centre) - want_from_tag))
                calliper = sx * sy
                area = piece[0] / scale**2
                perimeter = 2 * (sx + sy)
                rows.append({
                    "capture": path, "square": letter, "tray": tray, "cell": cell, "exposure_us": exposure,
                    "scale_px_per_mm": round(scale, 4), "scale_from": scale_from, "pixels": piece[0],
                    "area_mm2": round(area, 2), "calliper_mm2": round(calliper, 2),
                    "error_pct": round(100 * (area / calliper - 1), 3),
                    "edge_width_mm": round((area - calliper) / perimeter, 4),
                    "edge_width_px": round((area - calliper) / perimeter * scale, 3),
                    "from_tag_mm": round(math.dist(piece[1:], tag.centre) / scale, 1),
                    "x_px": round(piece[1], 1), "y_px": round(piece[2], 1),
                })
        print(f"{path}: {sum(r['capture'] == path for r in rows)} squares", file=sys.stderr, flush=True)
    with open(out / "squares.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"{'square':6} {'size':>5} {'stills':>6} {'error % median (range)':>26} {'edge width px median':>20} {'scale from'}")
    for letter, (sx, sy, tray, cell) in SQUARES.items():
        mine = [r for r in rows if r["square"] == letter]
        if not mine:
            print(f"{letter:6} not found")
            continue
        errors = [r["error_pct"] for r in mine]
        widths = [r["edge_width_px"] for r in mine]
        print(f"{letter:6} {round(sx):>5} {len(mine):>6} {statistics.median(errors):+9.2f} ({min(errors):+.2f} to {max(errors):+.2f})"
              f" {statistics.median(widths):>14.2f}       {mine[0]['scale_from']}, {mine[0]['from_tag_mm']} mm from tag")


if __name__ == "__main__":
    main(*sys.argv[1:4])
