"""Trays placed on a photo from the tag in their cell A1 (#220).

The method of metrology log 15.5h to 15.5l, written fresh from `experiments/round1-trays/shuffle.py`
(`place_any_rotation`): geometry on the tag detections, no image segmentation.

1. The tray's tag lies in cell A1, any way round. Its centre gives cell A1.
2. With 12 trays (4 x 5, portrait), A1 is at the south-west or the north-east corner. The two
   candidate tray centres are the tag centre plus and minus one offset common to every tray,
   turned by the tray's tilt and converted with the calibration's scale at the tag.
3. The candidate nearer a slot centre of the calibration's slot layout is taken; its slot and
   corner are the result.
4. The outline is the tray's measured outside size around that centre, turned by the tilt.

The tag's heading is never used for which way the tray faces, only for its tilt.
"""

import math
from collections import Counter
from dataclasses import dataclass, replace

from npec_rig.calibration import ScaleField
from npec_rig.tags import TRAY_ID_RANGE, TagDetection

# From the tag centre to the tray centre, mm, (right, up) in the frame of a tag lying with its top
# to the south (heading 180) on a tray with A1 at the south-west, turned by the tilt only. The median over 12 trays of 40 mm tags in cell A1, learned from the
# layout 1 stills of 20 October (metrology log 15.5l; every tray within 9.6 mm of it).
A1_TAG_TO_CENTRE_MM = (-104.0, -141.6)

# Outside size of a 4 x 5 tray in portrait, lip included, east-west by north-south, mm
# (tape measure, reference/trays.md).
TRAY_SIZE_MM = (305.0, 366.0)

# Below this difference between the two candidates' distances to their nearest slot, the corner
# is reported as a close call. A decision, not a measurement: the smallest difference seen over
# the 20 October shuffles was 103.4 mm (metrology log 15.5l).
CLOSE_CALL_MM = 50.0


@dataclass(frozen=True)
class TrayPlacement:
    """One tray, placed from its tag. Positions in full-size photo pixels."""

    tray_id: int
    centre: tuple[float, float]
    slot: str
    a1_corner: str  # "SW", or "NE" (tray turned 180)
    tilt_deg: float
    outline: tuple[tuple[float, float], ...]  # the tray's four outside corners, turned by the tilt
    margin_mm: float  # how much nearer a slot the chosen candidate is than the other
    status: str = "placed"  # or "close call", "two trays in one slot"


def _tilt_deg(tag: TagDetection) -> float:
    """The tray's turn off the image axes, clockwise: the tag's heading off the nearest right
    angle, taking the tag to lie square in its cell. The corners run top-left, top-right,
    bottom-right, bottom-left in the tag's own frame."""
    c = tag.corners
    up_x = (c[0][0] + c[1][0] - c[2][0] - c[3][0]) / 2
    up_y = (c[0][1] + c[1][1] - c[2][1] - c[3][1]) / 2
    heading = math.degrees(math.atan2(up_x, -up_y))
    return (heading + 45) % 90 - 45


def _outline(centre: tuple[float, float], tilt_deg: float, ppm: float) -> tuple[tuple[float, float], ...]:
    t = math.radians(tilt_deg)
    half_w, half_h = TRAY_SIZE_MM[0] / 2 * ppm, TRAY_SIZE_MM[1] / 2 * ppm
    across, down = (math.cos(t), math.sin(t)), (-math.sin(t), math.cos(t))
    return tuple(
        (centre[0] + a * half_w * across[0] + b * half_h * down[0], centre[1] + a * half_w * across[1] + b * half_h * down[1])
        for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )


def _nearest_slot(x: float, y: float, slots: list[dict]) -> tuple[str, float]:
    return min(((s["name"], math.hypot(s["centre"][0] - x, s["centre"][1] - y)) for s in slots), key=lambda s: s[1])


def place_trays(detections: list[TagDetection], scale_field: ScaleField, slots: list[dict]) -> list[TrayPlacement]:
    """Every tray tag in `detections` placed in a slot of `slots` (the calibration's slot layout,
    as `validation.slot_layout` gives it), in tag ID order."""
    out = []
    for tag in sorted(detections, key=lambda d: d.tag_id):
        if tag.tag_id not in TRAY_ID_RANGE:
            continue
        tilt = _tilt_deg(tag)
        ppm = scale_field.px_per_mm(*tag.centre)
        # The offset's frame in image pixels (y down): heading 180 turned by the tilt.
        t = math.radians(180 + tilt)
        right, up = (math.cos(t), math.sin(t)), (math.sin(t), -math.cos(t))
        dx = (A1_TAG_TO_CENTRE_MM[0] * right[0] + A1_TAG_TO_CENTRE_MM[1] * up[0]) * ppm
        dy = (A1_TAG_TO_CENTRE_MM[0] * right[1] + A1_TAG_TO_CENTRE_MM[1] * up[1]) * ppm
        candidates = []
        for corner, sign in (("SW", 1), ("NE", -1)):
            centre = (tag.centre[0] + sign * dx, tag.centre[1] + sign * dy)
            slot, distance = _nearest_slot(*centre, slots)
            candidates.append((distance, corner, centre, slot))
        (near, corner, centre, slot), (far, *_) = sorted(candidates)
        margin = (far - near) / ppm
        out.append(TrayPlacement(
            tray_id=tag.tag_id, centre=centre, slot=slot, a1_corner=corner, tilt_deg=tilt,
            outline=_outline(centre, tilt, ppm), margin_mm=margin,
            status="close call" if margin < CLOSE_CALL_MM else "placed",
        ))
    per_slot = Counter(p.slot for p in out)
    return [replace(p, status="two trays in one slot") if per_slot[p.slot] > 1 else p for p in out]
