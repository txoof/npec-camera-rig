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


def rotate_point(point: tuple[float, float], pivot: tuple[float, float], angle_deg: float) -> tuple[float, float]:
    """`point` rotated `angle_deg` clockwise in image coordinates (x right, y down) about `pivot`.

    Sign convention verified against a known synthetic rotation in test_tripwire.py, not assumed.
    """
    theta = np.radians(angle_deg)
    rotation = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    rotated = rotation @ (np.array(point) - np.array(pivot)) + np.array(pivot)
    return (float(rotated[0]), float(rotated[1]))


def rotate_detection(detection: TagDetection, pivot: tuple[float, float], angle_deg: float) -> TagDetection:
    """`detection` rigidly rotated `angle_deg` about an external `pivot` -- moves both the tag's
    position and its own orientation, as a whole-scene rotation (e.g. simulated camera roll)
    would. Use `pivot == detection.centre` to rotate a tag in place instead.
    """
    corners = tuple(rotate_point(p, pivot, angle_deg) for p in detection.corners)
    centre = rotate_point(detection.centre, pivot, angle_deg)
    return TagDetection(tag_id=detection.tag_id, corners=corners, centre=centre)


def sheet_detections(
    first_id: int, x0: float, y0: float, *, side_px: float = 120.0, pitch_px: float = 160.0,
    columns: int = 5, rows: int = 6,
) -> list[TagDetection]:
    """One printed calibration sheet: a `columns` x `rows` grid of square tags with consecutive
    IDs from `first_id`, top-left tag centred at (x0, y0)."""
    return [
        square_detection(first_id + r * columns + c, x0 + c * pitch_px, y0 + r * pitch_px, side_px)
        for r in range(rows)
        for c in range(columns)
    ]


def tray_layout_detections(
    *, shift: tuple[float, float] = (0.0, 0.0), side_px: float = 120.0
) -> list[TagDetection]:
    """12 sheets on 12 trays, 2 rows of 6 -- the tray-calibration layout. Sheets reuse the same 30
    IDs, as real reprinted sheets do; `shift` moves every sheet, as a validation round does."""
    dx, dy = shift
    return [
        d
        for row_y in (1000.0, 3500.0)
        for col in range(6)
        for d in sheet_detections(300, 800.0 + col * 1300.0 + dx, row_y + dy, side_px=side_px)
    ]
