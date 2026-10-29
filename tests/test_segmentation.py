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


# --- Touching trays (#282) ----------------------------------------------------------------------
# Where two tray outlines overlap, each plant pixel counts only for the tray whose centre is nearer
# (Aaron, 2026-10-23). Expected counts are worked out by hand from the pixel centres (pixel x
# covers x to x + 1), at an even 10 px/mm, so a pixel is 0.01 mm2.


def _even_scale():
    from npec_rig.calibration import scale_field_from_dict

    return scale_field_from_dict({"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": 10.0, "residual_std_pct": 0.0})


def _box(x0, y0, x1, y1):
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def test_plant_in_the_strip_two_touching_trays_share_is_counted_once_for_the_nearer_tray():
    """Tray A x 0 to 100, centre x 50; tray B x 80 to 180, centre x 130: they share x 80 to 100,
    and the point midway between the centres is x 90. A 10 x 10 px plant at x 85 to 95 lies in
    both: its columns 85 to 89 (centres 85.5 to 89.5) are nearer A, 90 to 94 nearer B."""
    from npec_rig.segmentation import measure_trays

    mask = np.zeros((100, 200), dtype=bool)
    mask[40:50, 85:95] = True

    a, b = measure_trays(mask, [(_box(0, 0, 100, 99), (50, 50)), (_box(80, 0, 180, 99), (130, 50))], _even_scale())
    assert (a.plant_px, b.plant_px) == (50, 50)
    assert (a.area_mm2, b.area_mm2) == (pytest.approx(0.5), pytest.approx(0.5))


def test_plant_inside_one_tray_only_stays_with_it_even_when_another_trays_centre_is_nearer():
    """Tray A x 0 to 100, y 0 to 100, centre (50, 50); a small tray B x 90 to 130, y 0 to 20,
    centre (110, 10), overlaps A's top right corner. A 5 x 5 px plant at x 92 to 97, y 5 to 10 lies
    in both and is nearer B. A 5 x 5 px plant at x 80 to 85, y 10 to 15 lies in A only, although
    B's centre is nearer (about 28 px against 50): it stays with A."""
    from npec_rig.segmentation import measure_trays

    mask = np.zeros((100, 200), dtype=bool)
    mask[5:10, 92:97] = True
    mask[10:15, 80:85] = True

    a, b = measure_trays(mask, [(_box(0, 0, 100, 99), (50, 50)), (_box(90, 0, 130, 20), (110, 10))], _even_scale())
    assert (a.plant_px, b.plant_px) == (25, 25)


def test_a_plant_pixel_exactly_midway_between_two_tray_centres_counts_once():
    """Review of #311: tray A centre x 50, tray B centre x 131, both outlines x 80 to 100. The
    midpoint, x 90.5, is the centre of pixel column 90, which is as near one tray as the other. A
    10 x 10 px plant at x 90 to 100 must still add up to 100 px across the two trays."""
    from npec_rig.segmentation import measure_trays

    mask = np.zeros((100, 200), dtype=bool)
    mask[40:50, 90:100] = True

    a, b = measure_trays(mask, [(_box(0, 0, 100, 99), (50, 50)), (_box(80, 0, 181, 99), (131, 50))], _even_scale())
    assert a.plant_px + b.plant_px == 100
