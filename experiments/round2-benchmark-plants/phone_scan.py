"""Benchmark rosettes from a phone scan scaled by callipers (#228, metrology log 17.13).

For each phone package (`<id>.ft2dphenodataset`), on its `analysis/analysis-input.png` and the
app's areas in pixels (`analysis/android_foliage.json`):

1. the base's four corners, from the yellow of its top face;
2. a homography onto a square of the calliper side, SIDE_MM;
3. each object's area in mm2 at the base plane: its app area times the homography's local area
   factor at its centre;
4. the height check: the four white beads at the rosette centres mapped onto the base plane, their
   neighbour spacings against SPACING_MM, and the mean of their squared ratios, the area factor
   at bead height. Reported, not applied: `at_beads_mm2` only shows what dividing by it gives.

Objects are named by where they lie on the base, in the base's own frame: the base turned so its
prism marker is at the north-west (15.1). In these photos that is the photo turned a quarter turn
clockwise: the NE rosette is at the photo's top left. Writes `results.csv` to DATA_DIR and one picture
per package, with the corners and beads found, to FIGURE_DIR.

Usage: phone_scan.py FIGURE_DIR DATA_DIR PACKAGE [PACKAGE ...]

A PACKAGE is a folder holding `analysis/analysis-input.png` and `analysis/android_foliage.json`.
"""
import csv
import itertools
import json
import math
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

SIDE_MM = 187.81  # mean of the four base sides, vernier calliper (Aaron, 2026-10-28)
SPACING_MM = 70.0  # rosette centre to centre, vernier calliper (Aaron, 2026-10-28)
# By the base-plane position of the object's centre, in the photo's frame: (left, top) half.
NAMES = {(True, True): "NE", (False, True): "SE", (True, False): "NW", (False, False): "SW"}


def base_corners(hsv: np.ndarray) -> np.ndarray:
    """The base's four corners, top-left, top-right, bottom-right, bottom-left, in image pixels:
    the largest yellow region's hull reduced to four points."""
    mask = cv2.inRange(hsv, (15, 120, 120), (35, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    hull = cv2.convexHull(max(contours, key=cv2.contourArea))
    quad = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True).reshape(-1, 2).astype(float)
    if len(quad) != 4:
        raise ValueError(f"base outline reduced to {len(quad)} points, not 4")
    # Clockwise from the corner nearest the image's top left, by angle around the centre, so a
    # base turned toward 45 degrees is still ordered right.
    centre = quad.mean(0)
    quad = quad[np.argsort(np.arctan2(quad[:, 1] - centre[1], quad[:, 0] - centre[0]))]
    return np.roll(quad, -int(quad.sum(1).argmin()), axis=0)


def to_base(h: np.ndarray, x: float, y: float) -> np.ndarray:
    q = h @ [x, y, 1.0]
    return q[:2] / q[2]


def area_factor(h: np.ndarray, x: float, y: float) -> float:
    """mm2 per pixel of homography `h` at image point (x, y): the determinant of its Jacobian."""
    p = h @ [x, y, 1.0]
    w = p[2]
    j = np.array([[h[0, 0] * w - p[0] * h[2, 0], h[0, 1] * w - p[0] * h[2, 1]],
                  [h[1, 0] * w - p[1] * h[2, 0], h[1, 1] * w - p[1] * h[2, 1]]]) / w**2
    return abs(np.linalg.det(j))


def beads(hsv: np.ndarray, corners: np.ndarray) -> list[tuple[float, float]]:
    """The four largest white blobs inside the base, away from its edge: the rosette beads.
    Raises ValueError unless there are at least four."""
    inside = np.zeros(hsv.shape[:2], np.uint8)
    cv2.fillPoly(inside, [corners.round().astype(np.int32)], 255)
    inside = cv2.erode(inside, np.ones((41, 41), np.uint8))
    white = cv2.inRange(hsv, (0, 0, 200), (180, 60, 255)) & inside
    n, _labels, stats, cents = cv2.connectedComponentsWithStats(white)
    if n - 1 < 4:
        raise ValueError(f"{n - 1} white blobs inside the base, not 4 beads")
    return [tuple(cents[i]) for i in sorted(range(1, n), key=lambda i: stats[i, cv2.CC_STAT_AREA])[-4:]]


def measure(package: Path, out_dir: Path) -> list[dict]:
    report = json.loads((package / "analysis/android_foliage.json").read_text())
    bgr = cv2.imread(str(package / "analysis/analysis-input.png"))
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    corners = base_corners(hsv)
    square = np.array([[0, 0], [SIDE_MM, 0], [SIDE_MM, SIDE_MM], [0, SIDE_MM]], np.float32)
    h = cv2.getPerspectiveTransform(corners.astype(np.float32), square)
    sides = [math.dist(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    found = beads(hsv, corners)
    on_base = [to_base(h, *b) for b in found]
    # The four sides of the square of beads, not its two diagonals (about 99 mm).
    spacings = sorted(math.dist(a, b) for a, b in itertools.combinations(on_base, 2))[:4]
    if max(spacings) > 1.2 * SPACING_MM or min(spacings) < 0.8 * SPACING_MM:
        raise ValueError(f"bead spacings {spacings} mm are not a square of about {SPACING_MM} mm")
    factor = statistics.mean((d / SPACING_MM) ** 2 for d in spacings)
    print(f"{package.name}: base sides {[round(v, 1) for v in sides]} px; bead spacings "
          f"{[round(d, 2) for d in spacings]} mm; area factor at bead height {factor:.4f}")
    rows = []
    outside = [t for t in report["traits"] if not 0 <= to_base(h, t["centroid"]["x"], t["centroid"]["y"])[1] <= SIDE_MM]
    if len(outside) != 1:
        raise ValueError(f"{len(outside)} objects off the base, expected the green square only")
    for t in report["traits"]:
        cx, cy = t["centroid"]["x"], t["centroid"]["y"]
        box = t["boundingBox"]
        # The rosettes whose bead lies in the app's box for this object: two when it merged them.
        held = sorted(NAMES[(bx_mm < SIDE_MM / 2, by_mm < SIDE_MM / 2)]
                      for (bx, by), (bx_mm, by_mm) in zip(found, on_base)
                      if box["x"] <= bx <= box["x"] + box["width"] and box["y"] <= by <= box["y"] + box["height"])
        name = "green square" if t is outside[0] else " + ".join(held)
        if not name:
            raise ValueError(f"object {t['id']} holds no bead")
        mm2 = t["areaPixels"] * area_factor(h, cx, cy)
        rows.append({"package": package.name.split(".")[0], "object": name, "area_px2": t["areaPixels"],
                     "base_mm2": round(mm2, 1), "bead_area_factor": round(factor, 4),
                     "at_beads_mm2": round(mm2 / factor, 1) if name != "green square" else ""})
    for x, y in corners:
        cv2.circle(bgr, (round(x), round(y)), 8, (255, 0, 255), 3)
    cv2.polylines(bgr, [corners.round().astype(np.int32)], True, (255, 0, 255), 2)
    for x, y in found:
        cv2.circle(bgr, (round(x), round(y)), 14, (255, 0, 255), 2)
    cv2.imwrite(str(out_dir / f"{package.name.split('-')[0]}-corners-beads.jpg"), bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return rows


def main() -> None:
    out_dir, data_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [r for p in sys.argv[3:] for r in measure(Path(p), out_dir)]
    with open(data_dir / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"  {r['package']}  {r['object']:13s} {r['area_px2']:6d} px2  {r['base_mm2']:7.1f} mm2 at the base  {r['at_beads_mm2']}")


if __name__ == "__main__":
    main()
