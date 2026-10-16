"""Tag detections the calibration and validation tests hand to `detect_tags` in place of real
photos."""

from tests.helpers import square_detection


# SyntheticBackend's frame has no real tags drawn into it, so `detect_tags` finds nothing on a
# plain capture -- exercising the "not enough tags" path for free. The happy path monkeypatches
# `detect_tags` with `square_detection`-built fixtures (same synthetic-geometry convention as
# test_calibration.py/test_tripwire.py), since drawing a real detectable tag into the frame isn't
# needed to test this module's own wiring.

CALIBRATION_TAGS = [
    square_detection(300 + i, cx, cy, side_px=40.0)
    for i, (cx, cy) in enumerate(
        [(200, 200), (1300, 200), (200, 950), (1300, 950), (750, 575), (500, 400)]
    )
]
CORNER_TAGS = [
    square_detection(450, 30, 30, side_px=60.0),
    square_detection(451, 1500, 30, side_px=60.0),
]


FOUR_CORNER_TAGS = [
    square_detection(450, 30, 30, side_px=60.0),
    square_detection(451, 1500, 30, side_px=60.0),
    square_detection(452, 1500, 1100, side_px=60.0),
    square_detection(455, 30, 1100, side_px=60.0),
]
