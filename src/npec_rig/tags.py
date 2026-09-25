"""AprilTag detection: cv2.aruco with the DetectorParameters the previous rig tuned on this
camera family (20 tags detected versus 12 with stock parameters, on a hard frame). Frozen on
purpose -- corner precision is the whole measurement, so changing these invalidates comparisons
against every calibration taken before. See PLAN.md's M2 section.
"""

from __future__ import annotations

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

# CLAUDE.md's calliper measurement of the tag that survived the rig rebuild: printed nominally
# 30mm, measured 29.3106mm. Reused for the CALIBRATION_ID_RANGE sheet (nominally also 30mm --
# reference/calibration-sheets/README.md) because that sheet has NOT itself been calliper-checked
# yet against its 2026-09-20 print run. Confirm with callipers before trusting a scale field built
# from it -- this is the single largest error source CLAUDE.md documents (~4.7% in area). The
# tripwire (tripwire.py) compares the corner tags' own image-plane geometry between two captures
# of this rig, never against an absolute mm figure, so it doesn't need this constant.
ASSUMED_CALIBRATION_TAG_SIZE_MM = 29.3106

# The corner tags' nominal printed size -- placeholder, NOT calliper-measured yet (same caution as
# ASSUMED_CALIBRATION_TAG_SIZE_MM above: the 30mm calibration tag measured 29.3106mm). Used only by
# the table-position view's outer-edge-to-centre conversion (app.py's run_calibration) -- an
# operator measures corner-tag-to-corner-tag with a tape measure laid outer-edge to outer-edge (no
# centre mark exists on a tag to measure to directly), and this constant converts that to the
# centre-to-centre distance TableFrame's aspect ratio actually needs. Overridable per run with a
# calliper measurement, same pattern as calibration_tag_size_mm.
ASSUMED_CORNER_TAG_SIZE_MM = 50.0


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
    array = np.array(corners)
    return float(np.linalg.norm(array - np.roll(array, -1, axis=0), axis=1).mean())


def tag_area_px(
    corners: tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]],
) -> float:
    """Exact pixel area of a tag's quadrilateral corners (shoelace formula) -- distinct from
    `tag_side_px(corners) ** 2`, which assumes the quad is a square with that mean side length.
    The two agree exactly for a true square; a keystoned (non-square) quad is where they diverge,
    which is the signal `calibration.area_scale_samples` reads.
    """
    array = np.array(corners)
    x, y = array[:, 0], array[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def detect_tags(frame: np.ndarray) -> list[TagDetection]:
    """Every AprilTag 36h11 in `frame`, sorted by tag id.

    `frame` is RGB (this project's convention throughout, see camera.py) or already grayscale.
    Channel order doesn't otherwise matter here -- `to_grayscale` handles it, and the detector
    only ever sees the grayscale result.
    """
    gray = to_grayscale(frame).astype(np.uint8) if frame.ndim == 3 else frame
    dictionary = cv2.aruco.getPredefinedDictionary(TAG_DICTIONARY)
    detector = cv2.aruco.ArucoDetector(dictionary, _detector_parameters())
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
    detections.sort(key=lambda d: d.tag_id)
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
