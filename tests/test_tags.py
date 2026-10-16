from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from npec_rig.tags import TAG_DICTIONARY, detect_tags, tag_area_px

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
