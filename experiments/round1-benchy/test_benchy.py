import math

import cv2
import numpy as np
import pytest

import benchy

pytestmark = pytest.mark.unit

YELLOW = (0, 210, 255)  # BGR
RED = (20, 20, 230)
MINT = (150, 210, 150)
BLUE = (200, 90, 20)


def patch(bgr, size=4):
    return np.full((size, size, 3), bgr, np.uint8)


def test_excess_green_takes_mint_leaves_not_yellow_red_or_blue():
    assert benchy.excess_green_mask(patch(MINT)).all()
    for colour in (YELLOW, RED, BLUE, (200, 200, 200)):
        assert not benchy.excess_green_mask(patch(colour)).any()


def test_red_mask_both_ends_of_hue_circle():
    assert benchy.red_mask(patch(RED)).all()
    assert benchy.red_mask(patch((60, 20, 230))).all()  # magenta side of red, hue near 175
    for colour in (YELLOW, MINT, BLUE):
        assert not benchy.red_mask(patch(colour)).any()


def test_area_mm2_is_pixels_over_scale_squared():
    m = np.zeros((10, 10), bool)
    m[:5, :4] = True  # 20 px
    assert benchy.area_mm2(m, 2.0) == pytest.approx(5.0)


def test_square_less_circular_than_disc():
    img = np.zeros((200, 400), np.uint8)
    cv2.rectangle(img, (20, 20), (120, 120), 1, -1)
    cv2.circle(img, (300, 70), 50, 1, -1)
    cs, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    by_x = sorted(cs, key=lambda c: c[:, 0, 0].mean())
    assert benchy.circularity(by_x[0]) < benchy.circularity(by_x[1])


def test_corners_go_clockwise_on_screen_from_the_prism():
    corners = benchy.corner_angles(math.pi / 4)  # prism at bottom right (y down)
    # bottom left, top left, top right in image coordinates
    assert benchy.nearest_corner(math.atan2(1, -1), corners) == "NE"
    assert benchy.nearest_corner(math.atan2(-1, -1), corners) == "SE"
    assert benchy.nearest_corner(math.atan2(-1, 1), corners) == "SW"
    assert benchy.nearest_corner(math.pi / 4 + 0.3, corners) == "NW"


def test_static_groups_split_on_move_turn_experiment_and_gaps():
    poses = [
        ("a", 100, 100, 45.0),
        ("a", 105, 102, 45.4),  # repeat
        ("a", 300, 100, 45.0),  # moved
        ("a", 300, 100, 135.0),  # turned
        ("b", 300, 100, 135.0),  # other experiment
        None,
        ("b", 300, 100, 135.0),  # after a failure, same pose as the last success
    ]
    assert benchy.static_groups(poses) == [0, 0, 1, 2, 3, None, 3]


def test_static_groups_turn_wraps_at_360():
    assert benchy.static_groups([("a", 0, 0, 359.8), ("a", 0, 0, 0.2)]) == [0, 0]
