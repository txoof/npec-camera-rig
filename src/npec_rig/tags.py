"""AprilTag detection: cv2.aruco with the DetectorParameters the previous rig tuned on this
camera family (20 tags detected versus 12 with stock parameters, on a hard frame). Frozen on
purpose -- corner precision is the whole measurement, so changing these invalidates comparisons
against every calibration taken before. See PLAN.md's M2 section.

Tray tags (TRAY_ID_RANGE) are read in a second pass with their own settings, which read the 20 mm
tray tags the frozen settings miss (metrology log 15.3c to 15.3e, issue #156). Every other tag
still comes from the frozen pass.
"""

from __future__ import annotations

import math

from dataclasses import dataclass

import cv2
import numpy as np

from npec_rig.camera import to_grayscale
from npec_rig.text_render import draw_text

TAG_DICTIONARY = cv2.aruco.DICT_APRILTAG_36h11

# Reserved 36h11 ID ranges (TODO.md, decided 2026-09-20 with Aaron, superseding the 2026-09-19
# allocation). Arbitrary -- chosen to be simple for future users, not measured or derived from
# anything. Uniqueness only needs to hold within one chamber, not across the fleet: different
# chambers may reuse the same tray IDs.
TRAY_ID_RANGE = range(0, 300)  # experimenters 3D-print their own
CALIBRATION_ID_RANGE = range(300, 450)
CORNER_ID_RANGE = range(450, 500)  # 4 tags mounted; exact IDs confirmed by detection, not by
# reading them off a photo. An earlier note here about one tag being partially obscured was
# stale -- all 4 are detected in every recent real run (verified against saved calibration
# artifacts).
RESERVED_ID_RANGE = range(500, 587)  # buffer for a future fixed rig-level role. 587 IDs total in
# 36h11 (0-586) -- verified against both cv2's dictionary size and moms_apriltag's TagGenerator2
# Id 500 was provisionally the auto-focus target; freed 2026-10-22 with the auto-focus bracket
# (PLAN.md, Tag ID allocation). No code treats it specially.

# Default size of the CALIBRATION_ID_RANGE sheets when a run gives no calliper reading. Callipers,
# 2026-09-29: the current 30mm sheets measure 30.0 +/- 0.1mm (see CLAUDE.md). The 29.3106mm figure
# older notes mention belonged to the previous rig's printed tags and does not apply. Tag size is a
# property of each print run, so every run should still pass its own calliper measurement
# (calibration_tag_size_mm); a wrong size here is the largest error source CLAUDE.md documents. The
# tripwire (tripwire.py) compares the corner tags' own image-plane geometry between two captures
# of this rig, never against an absolute mm figure, so it doesn't need this constant.
ASSUMED_CALIBRATION_TAG_SIZE_MM = 30.0


def _detector_parameters() -> cv2.aruco.DetectorParameters:
    params = cv2.aruco.DetectorParameters()
    # Corner precision is the whole measurement.
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    # The stock default rejects small tags: 12 detected on this camera family against 20+ with
    # this (previous rig's finding, reused rather than re-measured -- see PLAN.md M2).
    params.minMarkerPerimeterRate = 0.005
    params.adaptiveThreshWinSizeMin = 11
    params.adaptiveThreshWinSizeMax = 91
    params.adaptiveThreshWinSizeStep = 10
    return params


def _tray_detector_parameters() -> cv2.aruco.DetectorParameters:
    """The frozen parameters with finer bit sampling: each pattern square is read from 8 x 8 pixels
    instead of 4 x 4, ignoring a wider margin at its edge. On the 53 tag-test stills this read 273
    of 273 20 mm tray tag sightings against 218 with the frozen settings, found no tag that was not
    there, took the same time, and gave the same corners to 0.0 px on all 7 calibration stills
    (metrology log 15.3e). Calibration keeps the frozen pass anyway (Aaron, 2026-10-16); one pass
    with these settings for every tag is possible later, if the second pass's 4 s matters."""
    params = _detector_parameters()
    params.perspectiveRemovePixelPerCell = 8
    params.perspectiveRemoveIgnoredMarginPerCell = 0.2
    return params


@dataclass(frozen=True)
class TagDetection:
    """One AprilTag, located in one frame."""

    tag_id: int
    corners: tuple[
        tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]
    ]
    centre: tuple[float, float]


def tag_side_px(
    corners: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
) -> float:
    """Mean side length of a tag's quadrilateral corners, in pixels."""
    # Plain arithmetic, not numpy: four corners are too few for numpy to pay, and calibration and
    # validation call this tens of thousands of times (#169).
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    return (
        math.hypot(x1 - x0, y1 - y0) + math.hypot(x2 - x1, y2 - y1)
        + math.hypot(x3 - x2, y3 - y2) + math.hypot(x0 - x3, y0 - y3)
    ) / 4


def tag_area_px(
    corners: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
) -> float:
    """Exact pixel area of a tag's quadrilateral corners (shoelace formula) -- distinct from
    `tag_side_px(corners) ** 2`, which assumes the quad is a square with that mean side length.
    The two agree exactly for a true square; a keystoned (non-square) quad is where they diverge,
    which is the signal `calibration.area_scale_samples` reads.
    """
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = corners
    return float(0.5 * abs(
        (x0 * y1 + x1 * y2 + x2 * y3 + x3 * y0) - (y0 * x1 + y1 * x2 + y2 * x3 + y3 * x0)
    ))


def detect_tags(frame: np.ndarray) -> list[TagDetection]:
    """Every AprilTag 36h11 in `frame`, sorted by tag id. Tray tags come from a pass with
    `_tray_detector_parameters`, every other tag from the frozen `_detector_parameters` pass.

    `frame` is RGB (this project's convention throughout, see camera.py) or already grayscale.
    Channel order doesn't otherwise matter here -- `to_grayscale` handles it, and the detector
    only ever sees the grayscale result.
    """
    gray = to_grayscale(frame).astype(np.uint8) if frame.ndim == 3 else frame
    detections = [d for d in _detect(gray, _detector_parameters()) if d.tag_id not in TRAY_ID_RANGE]
    detections += [d for d in _detect(gray, _tray_detector_parameters()) if d.tag_id in TRAY_ID_RANGE]
    detections.sort(key=lambda d: d.tag_id)
    return detections


def _detect(gray: np.ndarray, params: cv2.aruco.DetectorParameters) -> list[TagDetection]:
    """Every tag one detector pass with `params` finds in the grayscale `gray`."""
    dictionary = cv2.aruco.getPredefinedDictionary(TAG_DICTIONARY)
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    corners_list, ids, _rejected = detector.detectMarkers(gray)

    detections = []
    if ids is not None:
        for tag_corners, tag_id in zip(corners_list, ids.flatten(), strict=True):
            corners = tag_corners.reshape(4, 2)
            centre = corners.mean(axis=0)
            detections.append(
                TagDetection(
                    tag_id=int(tag_id),
                    corners=tuple((float(x), float(y)) for x, y in corners),
                    centre=(float(centre[0]), float(centre[1])),
                )
            )
    return detections


def draw_overlay(frame: np.ndarray, detections: list[TagDetection]) -> np.ndarray:
    """`frame` with detected tags outlined and labelled, for a human to check in a browser."""
    overlay = frame.copy()
    color = (255, 0, 255)  # magenta, matches the focus-peaking convention in camera.py
    for detection in detections:
        points = np.array(detection.corners, dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(overlay, [points], isClosed=True, color=color, thickness=4)
        draw_text(
            overlay,
            str(detection.tag_id),
            (int(detection.centre[0]), int(detection.centre[1])),
            2.0,
            color,
        )
    return overlay
