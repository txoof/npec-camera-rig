"""Synthetic-detection builders shared across test modules -- exact-geometry fixtures, not photos,
same convention as test_tags.py/test_calibration.py.
"""

from __future__ import annotations

import numpy as np

from npec_rig.tags import TagDetection


def square_detection(tag_id: int, cx: float, cy: float, side_px: float) -> TagDetection:
    """A synthetic axis-aligned tag of exact known pixel size, centred at (cx, cy)."""
    half = side_px / 2
    corners = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    )
    return TagDetection(tag_id=tag_id, corners=corners, centre=(cx, cy))


def rotated_square_detection(
    tag_id: int, cx: float, cy: float, side_px: float, angle_deg: float
) -> TagDetection:
    """A synthetic tag of known pixel size, centred at (cx, cy), rotated `angle_deg` clockwise in
    image coordinates (x right, y down) about its own centre.
    """
    half = side_px / 2
    base = np.array([(-half, -half), (half, -half), (half, half), (-half, half)])
    theta = np.radians(angle_deg)
    # Clockwise in image coords (y down) is this sign convention -- verified by
    # test_tripwire.py's known-rotation tests, not assumed.
    rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    corners = base @ rotation.T + np.array([cx, cy])
    return TagDetection(
        tag_id=tag_id,
        corners=tuple((float(x), float(y)) for x, y in corners),
        centre=(cx, cy),
    )
