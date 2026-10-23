"""Plant masks through the Segmenter interface (#74).

The colours are mean RGB values of small patches of real photos, not values the code works out:
the benchmark plant's mint leaves and the tray, soil, pot, card and table around it in the still
of 23 October 2026 08:35:53 UTC of "Potato Plants v001" (experiment 18), 12 x 12 pixel patches at
full resolution.
"""

import numpy as np
import pytest

from npec_rig.segmentation import ExGSegmenter, HailoSegmenter, SegmenterUnavailable

pytestmark = pytest.mark.unit

PLANT = {"benchmark mint leaf": (156, 228, 188)}
NOT_PLANT = {
    "dark soil": (95, 58, 55),
    "pale soil": (146, 95, 88),
    "blue tray": (39, 88, 159),
    "blue tray in shade": (14, 49, 101),
    "black pot": (11, 10, 15),
    "yellow benchmark card": (254, 224, 54),
    "grey table": (235, 227, 240),
}


def _patch(rgb: tuple[int, int, int]) -> np.ndarray:
    return np.full((4, 4, 3), rgb, dtype=np.uint8)


@pytest.mark.parametrize("name", PLANT)
def test_green_threshold_takes_plant_colours(name):
    assert ExGSegmenter().segment(_patch(PLANT[name])).all()


@pytest.mark.parametrize("name", NOT_PLANT)
def test_green_threshold_leaves_out_tray_soil_pot_card_and_table(name):
    assert not ExGSegmenter().segment(_patch(NOT_PLANT[name])).any()


def test_hailo_segmenter_takes_the_same_call_and_says_it_is_not_available():
    with pytest.raises(SegmenterUnavailable, match="Hailo"):
        HailoSegmenter().segment(_patch(PLANT["benchmark mint leaf"]))
