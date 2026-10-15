"""Leaf area from a flatbed scan, scaled by the 30 mm AprilTags in the same scan (issue #162).

The scan's mm per px is measured from the tags in each direction (the scanner's two axes differ
by about 1%), not taken from its nominal dpi. Leaf = the round 1 green test (excess green above
0.1, green above red), largest piece plus any piece touching it; holes in the leaf stay holes.

    python3 experiments/round1-leaves/scan_area.py experiments/round1-leaves/scans/*.jpg
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

TAG_MM = 30.0  # current 30 mm sheets measure 30.0 +/- 0.1 mm (CLAUDE.md Facts)
EXG_MIN = 0.1


def excess_green_mask(bgr: np.ndarray, exg_min: float = EXG_MIN) -> np.ndarray:
    f = bgr.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    return ((2 * g - r - b) / (b + g + r + 1e-6) > exg_min) & (g > r)


def tag_scale(gray: np.ndarray) -> tuple[float, float, int, float]:
    """(px per mm along x, along y, tags used, spread of the per-tag x and y scales in %)."""
    ar = cv2.aruco
    det = ar.ArucoDetector(ar.getPredefinedDictionary(ar.DICT_APRILTAG_36h11), ar.DetectorParameters())
    corners, ids, _ = det.detectMarkers(gray)
    if ids is None:
        raise ValueError("no tags in the scan")
    sx, sy = [], []
    for q in corners:
        q = q[0]
        edges = [q[(i + 1) % 4] - q[i] for i in range(4)]
        # Each edge's length split onto the image axes by its direction.
        for e in edges:
            (sx if abs(e[0]) > abs(e[1]) else sy).append(np.hypot(*e) / TAG_MM)
    spread = 100 * max(np.std(sx) / np.mean(sx), np.std(sy) / np.mean(sy))
    return float(np.mean(sx)), float(np.mean(sy)), len(ids), float(spread)


def leaf_mask(bgr: np.ndarray) -> np.ndarray:
    m = excess_green_mask(bgr).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    big = 1 + int(np.argmax(st[1:, 4]))
    return lab == big


def main(paths: list[str]) -> None:
    print("scan,leaf_px,px_per_mm_x,px_per_mm_y,tags,tag_scale_spread_pct,leaf_mm2")
    for p in paths:
        im = cv2.imread(p)
        sx, sy, n, spread = tag_scale(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))
        m = leaf_mask(im)
        px = int(m.sum())
        print(f"{Path(p).stem},{px},{sx:.3f},{sy:.3f},{n},{spread:.2f},{px / (sx * sy):.1f}")
        out = im.copy()
        out[m] = (out[m] * 0.4 + np.array([255, 0, 255]) * 0.6).astype(np.uint8)
        s = 1000 / max(out.shape[:2])
        cv2.imwrite(str(Path(sys.argv[0]).parent / "overlays" / f"scan_{Path(p).stem}.jpg"),
                    cv2.resize(out, None, fx=s, fy=s, interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    main(sys.argv[1:])
