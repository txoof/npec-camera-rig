import pytest

import shuffle

pytestmark = pytest.mark.unit


def test_corner_sw_near_the_sw_heading_and_ne_when_turned():
    assert shuffle.corner(178.0, 180.0) == "SW"
    assert shuffle.corner(3.0, 180.0) == "NE"
    assert shuffle.corner(359.0, 180.0) == "NE"


def test_tilt_is_the_heading_off_a_right_angle():
    assert shuffle.tilt(183.0) == 3.0
    assert shuffle.tilt(357.0) == -3.0


def test_rounds_split_where_stills_are_far_apart():
    stills = [{"t": t} for t in (0, 3, 6, 200, 203, 500)]
    assert [len(g) for g in shuffle.rounds_by_gap(stills, 60)] == [3, 2, 1]
