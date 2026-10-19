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


# The 15.5h offset with A1 at SW puts the tray centre 107.8 mm east and 149.1 mm north of the tag
# (image y down), whatever way round the tag lies (15.5j).
SLOTS = [{"name": "N1", "centre": (1108.0, 851.0)}, {"name": "S1", "centre": (892.0, 1149.0)}]


@pytest.mark.parametrize("heading", [0.0, 90.0, 180.0, 270.0, 183.0])
def test_any_rotation_takes_the_candidate_on_a_slot(heading):
    slots = [SLOTS[0], {"name": "far", "centre": (5000.0, 5000.0)}]
    p = shuffle.place_any_rotation(1000.0, 1000.0, heading, 1.0, slots, shuffle.TRAY_TYPES[shuffle.TRAY_TYPE])
    assert (p["slot"], p["a1"]) == ("N1", "SW")


def test_any_rotation_picks_ne_when_that_candidate_is_on_a_slot():
    slots = [SLOTS[1], {"name": "far", "centre": (5000.0, 5000.0)}]
    p = shuffle.place_any_rotation(1000.0, 1000.0, 0.0, 1.0, slots, shuffle.TRAY_TYPES[shuffle.TRAY_TYPE])
    assert (p["slot"], p["a1"]) == ("S1", "NE")
