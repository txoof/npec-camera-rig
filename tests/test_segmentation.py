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


# --- Plant per cell (#364) ------------------------------------------------------------------------
# Two cells side by side at an even 10 px/mm, each 40 px square, a 10 px wall between them:
# cell A1 covers x 10 to 50, cell B1 x 60 to 100, both y 10 to 50. One pixel is 0.01 mm2.


def _cells():
    from npec_rig.tray_placement import Cell

    return [
        Cell("A1", (30.0, 30.0), _box(10, 10, 50, 50), "plant"),
        Cell("B1", (80.0, 30.0), _box(60, 10, 100, 50), "plant"),
    ]


def test_a_plant_inside_one_cell_counts_for_that_cell_only() -> None:
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    mask[20:30, 20:30] = True  # 100 px inside A1
    a1, b1 = measure_cells(mask, _cells(), _even_scale())
    assert (a1.plant_px, a1.area_mm2) == (100, pytest.approx(1.0))
    assert (b1.plant_px, b1.area_mm2, b1.centre_px) == (0, 0.0, None)


def test_a_leaf_hanging_over_the_wall_counts_wholly_for_the_cell_holding_most_of_it() -> None:
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    # One piece, rows 20 to 29: x 40 to 50 inside A1 (11 columns), x 51 to 54 over the wall (4
    # columns): 150 px, all for A1.
    mask[20:30, 40:55] = True
    a1, b1 = measure_cells(mask, _cells(), _even_scale())
    assert (a1.plant_px, a1.area_mm2) == (150, pytest.approx(1.5))
    assert b1.plant_px == 0


def test_a_strip_lying_on_the_wall_only_counts_for_no_cell() -> None:
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    mask[15:45, 53:57] = True  # x 53 to 56: inside the wall (x 51 to 59), touching neither cell
    assert [m.plant_px for m in measure_cells(mask, _cells(), _even_scale())] == [0, 0]


def test_one_piece_across_two_cells_counts_wholly_for_the_cell_holding_more_of_it() -> None:
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    # Rows 20 to 29, x 45 to 74: in A1 x 45 to 50 (6 columns), in B1 x 60 to 74 (15 columns),
    # 300 px in all, all for B1.
    mask[20:30, 45:75] = True
    a1, b1 = measure_cells(mask, _cells(), _even_scale())
    assert (a1.plant_px, b1.plant_px) == (0, 300)


def test_a_piece_covering_a_second_cells_opening_marks_both_cells_leaves_over_other_cells() -> None:
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    mask[20:30, 45:75] = True  # 60 px in A1, 150 px in B1: B1 holds it, A1's opening is covered
    a1, b1 = measure_cells(mask, _cells(), _even_scale())
    assert (a1.over_other_cells, b1.over_other_cells) == (True, True)


def test_pieces_each_within_their_own_cell_mark_no_cell() -> None:
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    mask[20:30, 20:30] = True  # inside A1
    mask[20:30, 70:80] = True  # inside B1
    a1, b1 = measure_cells(mask, _cells(), _even_scale())
    assert (a1.plant_px, b1.plant_px, a1.over_other_cells, b1.over_other_cells) == (100, 100, False, False)


def test_a_piece_reaching_past_its_trays_outline_counts_only_inside_the_outline() -> None:
    """Review of #374: a neighbouring tray's plant (a 1 x 1 tray has no cells) reaching into A1
    must not bring its whole area. The tray outline ends at x 55: the piece at x 40 to 99, rows 20
    to 29, is 600 px, 150 of them (x 40 to 54) inside the outline."""
    from npec_rig.segmentation import measure_cells

    mask = np.zeros((60, 110), dtype=bool)
    mask[20:30, 40:100] = True
    [a1] = measure_cells(mask, _cells()[:1], _even_scale(), outline_px=_box(0, 0, 54.5, 59))
    assert a1.plant_px == 150


# --- Grow from leaf cores (#363, metrology log 24.8 and 33.1) ---------------------------------------
# A painted tray box, 400 x 400 px. The cutoffs are worked out by hand from the method as written in
# the metrology log: the soil's greenness (2G - R - B) / (R + G + B) falls in a 0.01 bin, the soil
# level is that bin's centre, the lower cutoff 0.07 above it and never below -0.045.
SOIL_LOW = (110, 100, 100)  # greenness -0.032: bin centre -0.035, lower cutoff 0.035
SOIL_HIGH = (100, 100, 90)  # greenness 0.034: bin centre 0.035, lower cutoff 0.105
PALE_EDGE = (150, 165, 140)  # greenness 0.088: above 0.035, below 0.105, below the core's 0.1
GREENISH_SOIL = (120, 125, 105)  # greenness 0.071: above 0.035, never a core
TAG_CORNERS = ((300, 60), (340, 60), (340, 100), (300, 100))  # 40 px square, centre (320, 80)


def _painted_tray(soil) -> np.ndarray:
    box = np.full((400, 400, 3), soil, dtype=np.uint8)
    box[:30, :] = NOT_PLANT["blue tray"]  # the tray's rim
    box[92:168, 92:208] = PALE_EDGE  # the leaf's pale edge, 8 px wide
    box[100:160, 100:200] = PLANT["benchmark mint leaf"]  # the leaf
    box[168:180, 92:208] = NOT_PLANT["blue tray"]  # blue plastic touching the leaf's edge
    box[250:300, 250:320] = GREENISH_SOIL  # touching no leaf
    box[70:90, 310:330] = PLANT["benchmark mint leaf"]  # leaf colour on the tag, inside its square
    return box


@pytest.mark.parametrize(("soil", "soil_level", "cutoff", "edge_in"), [
    (SOIL_LOW, -0.035, 0.035, True), (SOIL_HIGH, 0.035, 0.105, False)])
def test_grow_from_leaf_cores_joins_a_pale_edge_to_its_leaf_and_leaves_out_soil_blue_and_the_tag(
    soil, soil_level, cutoff, edge_in
) -> None:
    from npec_rig.segmentation import grow_from_cores

    inside = np.ones((400, 400), dtype=bool)
    grown = grow_from_cores(_painted_tray(soil), inside, tag_corners=[TAG_CORNERS])

    assert grown.soil_level == pytest.approx(soil_level, abs=1e-9)
    assert grown.lower_cutoff == pytest.approx(cutoff, abs=1e-9)
    assert grown.mask[100:160, 100:200].all()  # the leaf
    assert grown.mask[92:100, 92:208].all() == edge_in  # its pale edge, joined with the low cutoff only
    assert not grown.mask[168:180].any()  # the blue plastic
    assert not grown.mask[:30].any()  # the rim
    assert not grown.mask[250:300, 250:320].any()  # greenish soil touching no leaf
    assert not grown.mask[48:112, 288:352].any()  # the tag's square enlarged 1.6 times
    assert grown.mask.sum() == (100 * 60 if not edge_in else 116 * 76)  # the leaf, with its edge or not


def test_grow_from_leaf_cores_counts_nothing_outside_the_tray_outline() -> None:
    from npec_rig.segmentation import grow_from_cores

    inside = np.ones((400, 400), dtype=bool)
    inside[:, 150:] = False
    grown = grow_from_cores(_painted_tray(SOIL_LOW), inside)
    assert not grown.mask[:, 150:].any()
    assert grown.mask[100:160, 100:150].all()
