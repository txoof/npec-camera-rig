"""Focus check against a static reference tag (tag 500, 60 mm, fixed at the north table edge).

During an experiment nobody re-validates, so a change in where the lens physically lands (after a
restart, a power cut, or the drive back after a capture) has to show in the photographs
themselves. Measured 2026-10-06 (docs/metrology-log.md, runs 3e and 3f): with the lens reported at
the same position, the calibration tags' readings moved by up to 1.7 points depending on the
lens's history. Tag 500's sharpness follows such a change (+72% and -21% for a lens change that
moved the readings +0.6 and -1.0 points, about 2% between repeated photographs); its apparent
area does not (changes of the same size as its repeat noise, 0.25%).

So every full-res capture measures the sharpness of a square around tag 500, at the position
recorded when the reference was set, and compares it with the reference value. It says that
focus changed, not by how many points: the relation is not a straight line. It also responds to
a change of lighting. The position is reused rather than searched for each time (searching the
full photograph takes 5.3 s; this takes about 4 ms); the corner-tag tripwire is what says the
camera itself has not moved.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from npec_rig.camera import laplacian_variance, to_grayscale
from npec_rig.settings import load_settings, save_setting
from npec_rig.tags import TagDetection

REFERENCE_TAG_ID = 500
SQUARE_HALF_PX = 250  # 500 px square, about 2 tag widths at 4.8 px/mm
# Decision, from the 2026-10-06 data: repeated photographs differ by about 2%, a 0.1 lens change
# by 21% or more, and an app restart that moved the readings 0.4 points by 11%.
CHANGE_LIMIT_PCT = 10.0
SETTING = "FocusReference"


def sharpness_at(frame: np.ndarray, x: int, y: int) -> float:
    """Laplacian variance of the square centred on (x, y), clipped to the frame."""
    h, w = frame.shape[:2]
    x0, x1 = max(0, x - SQUARE_HALF_PX), min(w, x + SQUARE_HALF_PX)
    y0, y1 = max(0, y - SQUARE_HALF_PX), min(h, y + SQUARE_HALF_PX)
    return laplacian_variance(to_grayscale(frame[y0:y1, x0:x1].astype(np.float32)))


def find_reference_tag(detections: list[TagDetection]) -> TagDetection | None:
    return next((d for d in detections if d.tag_id == REFERENCE_TAG_ID), None)


def load_reference() -> dict | None:
    return load_settings().get(SETTING)


def set_reference(frame: np.ndarray, detections: list[TagDetection], capture: str) -> dict:
    """Record tag 500's position and sharpness in `frame` as the reference. Raises LookupError
    if tag 500 is not in `detections`, ValueError if the square around it shows no detail."""
    tag = find_reference_tag(detections)
    if tag is None:
        raise LookupError(f"tag {REFERENCE_TAG_ID} is not in this photograph")
    x, y = (int(round(v)) for v in tag.centre)
    sharpness = sharpness_at(frame, x, y)
    if sharpness <= 0:
        raise ValueError("the square around the tag shows no detail (too dark, or out of view)")
    reference = {
        "x": x,
        "y": y,
        "sharpness": sharpness,
        "set_at": datetime.now(timezone.utc).isoformat(),
        "capture": capture,
    }
    save_setting(SETTING, reference)
    return reference


def check(frame: np.ndarray, reference: dict | None) -> dict:
    """Compare the sharpness at the reference position with the reference value."""
    if reference is None:
        return {"verdict": "NO REFERENCE", "sharpness": None, "change_pct": None}
    sharpness = sharpness_at(frame, reference["x"], reference["y"])
    change_pct = 100.0 * (sharpness / reference["sharpness"] - 1.0)
    return {
        "verdict": "CHANGED" if abs(change_pct) > CHANGE_LIMIT_PCT else "OK",
        "sharpness": sharpness,
        "change_pct": change_pct,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


_last_check: dict | None = None


def record(frame: np.ndarray) -> dict:
    """Check `frame` against the stored reference and remember the result as the latest."""
    global _last_check
    _last_check = check(frame, load_reference())
    return _last_check


def last_check() -> dict | None:
    return _last_check
