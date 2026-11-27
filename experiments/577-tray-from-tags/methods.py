"""Methods B and C of metrology log 56, for comparison against the app's method A.

B places each tray from its own tag alone. C starts from B, nudges each tray onto the blue rim
beside it, and then accounts for the blue: plastic no tray covers, and trays that overlap, are
leftover and are flagged. Research code: it imports `npec_rig`, nothing imports it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from npec_rig.tray_placement import (
    A1_TAG_TO_CENTRE_MM,
    TRAY_ID_RANGE,
    TRAY_SIZE_MM,
    _blue_rim,
    _heading_deg,
    _tilt_deg,
    tray_outline_at,
)

# How far the nudge may move a tray from where its tag put it, mm. The tag places a tray to about
# 10 mm (metrology log 15.5l) and the blue rim to about 3 mm (log 20), so a move beyond this is
# not a correction, it is a different tray. A decision, not a measurement.
NUDGE_MM = 25.0
# Step of the nudge search, mm. Finer than the blue finder's own spread.
NUDGE_STEP_MM = 2.0
# The rim band drawn along each side of a tray's outline when scoring blue coverage, mm. The tray
# wall measures 11 to 13 mm (review of #281).
RIM_BAND_MM = 9.0
# Blue left over, as a share of one tray's area, before the photo is called unexplained. A
# decision, not a measurement.
LEFTOVER_TRAY_SHARE = 0.25
# Two placed trays overlapping by more than this share of a tray are flagged.
OVERLAP_SHARE = 0.10


@dataclass(frozen=True)
class Placed:
    tray_id: int | None
    centre: tuple[float, float]
    corners: tuple[tuple[float, float], ...]
    tilt_deg: float
    moved_mm: float
    ring: float


def _tray_tags(detections):
    return [t for t in detections if t.tag_id in TRAY_ID_RANGE]


def _centre_from_tag(tag, ppm, corner_sign=1):
    """Where the tray's centre lies from its tag, taking the tag to lie in cell A1 (4 x 5 trays).
    `corner_sign` -1 is the other corner, for a tray laid the other way round."""
    tilt = _tilt_deg(tag)
    t = math.radians(180 + tilt)
    right, up = (math.cos(t), math.sin(t)), (math.sin(t), -math.cos(t))
    dx = (A1_TAG_TO_CENTRE_MM[0] * right[0] + A1_TAG_TO_CENTRE_MM[1] * up[0]) * ppm
    dy = (A1_TAG_TO_CENTRE_MM[0] * right[1] + A1_TAG_TO_CENTRE_MM[1] * up[1]) * ppm
    return (tag.centre[0] + corner_sign * dx, tag.centre[1] + corner_sign * dy), tilt


def place_from_tags(detections, scale_field, factor):
    """Method B: each tray placed from its own tag, in full-size photo pixels. The blue is not
    used, so a tray with no readable tag is not placed at all."""
    out = []
    for tag in sorted(_tray_tags(detections), key=lambda d: d.tag_id):
        ppm = scale_field.px_per_mm(*tag.centre)
        centre, tilt = _centre_from_tag(tag, ppm)
        out.append(Placed(tag.tag_id, centre, tray_outline_at(centre, tilt, ppm), tilt, 0.0, float("nan")))
    return out


def _ring_mask(shape, corners, band_px):
    """A mask of the band just inside a tray's outline, where its lit rim shows."""
    outer = np.zeros(shape, np.uint8)
    cv2.fillConvexPoly(outer, np.round(corners).astype(np.int32), 1)
    inner = cv2.erode(outer, np.ones((3, 3), np.uint8), iterations=max(1, int(round(band_px / 2))))
    return outer - inner


def _ring_score(rim, corners, band_px):
    ring = _ring_mask(rim.shape, corners, band_px)
    n = int(ring.sum())
    return 0.0 if n == 0 else float((rim & ring.astype(bool)).sum()) / n


def nudge_onto_blue(placed, rim, scale_field, factor):
    """Method C's nudge: the tray moved, within `NUDGE_MM`, to where its rim band covers the most
    blue. `rim` is the blue rim mask of the small image; `factor` its scale to full size."""
    ppm_small = scale_field.px_per_mm(*placed.centre) / factor
    band = max(2.0, RIM_BAND_MM * ppm_small)
    step = max(1.0, NUDGE_STEP_MM * ppm_small)
    reach = NUDGE_MM * ppm_small
    small = np.asarray(placed.corners, float) / factor
    best, best_d = None, (0.0, 0.0)
    offsets = np.arange(-reach, reach + step / 2, step)
    for dy in offsets:
        for dx in offsets:
            if math.hypot(dx, dy) > reach:
                continue
            s = _ring_score(rim, small + (dx, dy), band)
            if best is None or s > best:
                best, best_d = s, (dx, dy)
    moved = math.hypot(*best_d) / ppm_small
    corners = tuple((x + best_d[0] * factor, y + best_d[1] * factor) for x, y in placed.corners)
    centre = (placed.centre[0] + best_d[0] * factor, placed.centre[1] + best_d[1] * factor)
    return Placed(placed.tray_id, centre, corners, placed.tilt_deg, moved, best or 0.0)


def leftover(rim, placed_list, scale_field, factor):
    """Blue the placed trays do not account for, and trays that overlap, as shares of one tray."""
    covered = np.zeros(rim.shape, np.uint8)
    for p in placed_list:
        cv2.fillConvexPoly(covered, np.round(np.asarray(p.corners, float) / factor).astype(np.int32), 1)
    blue = rim.astype(bool)
    left = int((blue & ~covered.astype(bool)).sum())
    ppm_small = scale_field.px_per_mm(rim.shape[1] * factor / 2, rim.shape[0] * factor / 2) / factor
    tray_px = TRAY_SIZE_MM[0] * ppm_small * TRAY_SIZE_MM[1] * ppm_small
    overlaps = 0
    for i, a in enumerate(placed_list):
        for b in placed_list[i + 1:]:
            ca = np.round(np.asarray(a.corners, float) / factor).astype(np.float32)
            cb = np.round(np.asarray(b.corners, float) / factor).astype(np.float32)
            area, _ = cv2.intersectConvexConvex(ca, cb)
            if area > OVERLAP_SHARE * tray_px:
                overlaps += 1
    return {"leftover_blue_px": left, "leftover_share": left / tray_px if tray_px else 0.0,
            "overlapping_pairs": overlaps}


def place_tags_then_blue(detections, image, scale_field, factor):
    """Method C: tags anchor, blue explains the rest."""
    rim = _blue_rim(image)
    first = place_from_tags(detections, scale_field, factor)
    moved = [nudge_onto_blue(p, rim, scale_field, factor) for p in first]
    return moved, leftover(rim, moved, scale_field, factor)
