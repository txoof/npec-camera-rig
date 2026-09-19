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

TAG_DICTIONARY = cv2.aruco.DICT_APRILTAG_36h11

# Reserved 36h11 ID ranges (TODO.md, decided 2026-09-19 with Aaron). Arbitrary -- chosen to be
# non-overlapping and roomy, not measured or derived from anything. Uniqueness only needs to hold
# within one chamber, not across the fleet: different chambers may reuse the same tray IDs.
CALIBRATION_ID_RANGE = range(0, 25)
UNALLOCATED_ID_RANGE = range(25, 70)  # buffer for a future fixed rig-level role
CORNER_ID_RANGE = range(70, 80)  # 4 tags mounted (one currently partially obscured); exact IDs
# confirmed by detection, not by reading them off a photo
TRAY_ID_RANGE = range(100, 587)  # 587 IDs total in 36h11 (0-586) -- verified against cv2's own
# dictionary size, not trusted from memory


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


def detect_tags(frame: np.ndarray) -> list[TagDetection]:
    """Every AprilTag 36h11 in `frame`, sorted by tag id.

    `frame` is RGB (this project's convention throughout, see camera.py) or already grayscale.
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
        cv2.putText(
            overlay,
            str(detection.tag_id),
            (int(detection.centre[0]), int(detection.centre[1])),
            cv2.FONT_HERSHEY_SIMPLEX,
            2.0,
            color,
            4,
            cv2.LINE_AA,
        )
    return overlay
