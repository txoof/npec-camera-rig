from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from npec_rig import tags
from npec_rig.tags import TAG_DICTIONARY, TagDetection, detect_tags, tag_area_px

pytestmark = pytest.mark.unit

# A small crop from a real bench photo, containing exactly one genuine, isolated AprilTag (id 76).
# Deliberately narrow: it exists to prove our code decodes real camera/JPEG output, not synthetic
# bitmaps -- it is not a representative sample of the rig's typical lighting or focus, and no
# other test should assume anything about its contents beyond "one real tag is in here".
REAL_TAG_CROP = Path(__file__).parent / "fixtures" / "tags" / "real_tag_crop.jpg"
REAL_TAG_CROP_ID = 76


def _generate_tag(tag_id: int, *, tag_size: int = 200, border: int = 60) -> np.ndarray:
    """A known AprilTag, rendered by cv2's own generator -- not our own tag-drawing code.

    `border` adds the white quiet zone the detector needs to find the tag's edge; a bare
    `generateImageMarker` output touches the image border and is not detected.
    """
    dictionary = cv2.aruco.getPredefinedDictionary(TAG_DICTIONARY)
    tag = cv2.aruco.generateImageMarker(dictionary, tag_id, tag_size)
    return cv2.copyMakeBorder(tag, border, border, border, border, cv2.BORDER_CONSTANT, value=255)


def test_detects_a_known_generated_tag() -> None:
    detections = detect_tags(_generate_tag(5))
    assert [d.tag_id for d in detections] == [5]
    assert len(detections[0].corners) == 4


def test_detects_multiple_known_tags_sorted_by_id() -> None:
    tag_a = _generate_tag(3, border=20)
    tag_b = _generate_tag(9, border=20)
    # Side by side, each still has its own white quiet zone from the per-tag border.
    frame = np.hstack([tag_a, tag_b])
    detections = detect_tags(frame)
    assert [d.tag_id for d in detections] == [3, 9]


@pytest.mark.parametrize("angle", [15, 90, 180, 260])
def test_detects_a_known_tag_at_various_rotations(angle: int) -> None:
    """AprilTags are designed to decode at any rotation -- this checks our corner/id handling
    doesn't secretly assume one orientation, not the detector's own rotation invariance."""
    tag = _generate_tag(11)
    centre = (tag.shape[1] / 2, tag.shape[0] / 2)
    rotation = cv2.getRotationMatrix2D(centre, angle, 1.0)
    rotated = cv2.warpAffine(
        tag, rotation, (tag.shape[1], tag.shape[0]), borderValue=255
    )
    detections = detect_tags(rotated)
    assert [d.tag_id for d in detections] == [11]
    assert len(detections[0].corners) == 4


def test_detects_a_real_photographed_tag() -> None:
    """One narrow real-world smoke check: genuine camera/JPEG output decodes, not just
    synthetically rendered bitmaps. Not a claim about typical lighting or focus."""
    frame = np.array(Image.open(REAL_TAG_CROP).convert("RGB"))
    detections = detect_tags(frame)
    assert REAL_TAG_CROP_ID in [d.tag_id for d in detections]


def _parameter_values(params: cv2.aruco.DetectorParameters) -> dict:
    return {
        name: getattr(params, name)
        for name in dir(params)
        if not name.startswith("_") and not callable(getattr(params, name))
    }


def test_frozen_detector_parameters_are_unchanged() -> None:
    """Calibration compares against every earlier calibration, so its settings stay as they were
    (#156 added tray settings beside them, not instead of them)."""
    values = _parameter_values(tags._detector_parameters())
    stock = _parameter_values(cv2.aruco.DetectorParameters())
    tuned = {
        "cornerRefinementMethod": cv2.aruco.CORNER_REFINE_SUBPIX,
        "minMarkerPerimeterRate": 0.005,
        "adaptiveThreshWinSizeMin": 11,
        "adaptiveThreshWinSizeMax": 91,
        "adaptiveThreshWinSizeStep": 10,
    }
    assert values == {**stock, **tuned}


def test_tray_detector_parameters_differ_only_in_bit_sampling() -> None:
    frozen = _parameter_values(tags._detector_parameters())
    tray = _parameter_values(tags._tray_detector_parameters())
    changed = {name: value for name, value in tray.items() if frozen[name] != value}
    assert changed == pytest.approx(
        {"perspectiveRemovePixelPerCell": 8, "perspectiveRemoveIgnoredMarginPerCell": 0.2}
    )


def test_detects_a_tray_tag_and_a_calibration_tag_in_one_frame() -> None:
    frame = np.hstack([_generate_tag(5, border=20), _generate_tag(350, border=20)])
    assert [d.tag_id for d in detect_tags(frame)] == [5, 350]


def test_tray_tags_come_from_the_tray_pass_and_others_from_the_frozen_pass(monkeypatch) -> None:
    """Each pass finds tag 5 (a tray tag) and tag 350 (a calibration tag) at its own corners; the
    result must take 5 from the tray pass and 350 from the frozen pass."""

    def fake_detect(gray, params):
        offset = 100.0 if params.perspectiveRemovePixelPerCell == 8 else 0.0
        return [
            TagDetection(tag_id, ((offset, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), (offset, 0.0))
            for tag_id in (350, 5)
        ]

    monkeypatch.setattr(tags, "_detect", fake_detect)
    detections = detect_tags(np.zeros((10, 10), dtype=np.uint8))
    assert [(d.tag_id, d.centre[0]) for d in detections] == [(5, 100.0), (350, 0.0)]


def test_tag_area_px_of_a_square_is_side_squared() -> None:
    corners = ((0.0, 0.0), (120.0, 0.0), (120.0, 120.0), (0.0, 120.0))
    assert tag_area_px(corners) == pytest.approx(120.0**2)


def test_tag_area_px_of_a_rectangle_is_width_times_height() -> None:
    # Deliberately not a square: this is exactly the case tag_side_px (mean side length) squared
    # would get wrong, which is the whole point of computing area separately (shoelace formula).
    corners = ((0.0, 0.0), (180.0, 0.0), (180.0, 88.0), (0.0, 88.0))
    assert tag_area_px(corners) == pytest.approx(180.0 * 88.0)


def test_tag_area_px_is_invariant_to_winding_order() -> None:
    corners = ((0.0, 0.0), (0.0, 120.0), (120.0, 120.0), (120.0, 0.0))  # clockwise, not CCW
    assert tag_area_px(corners) == pytest.approx(120.0**2)
