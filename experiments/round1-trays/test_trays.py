import json
import cv2
import numpy as np
import pytest

import trays

pytestmark = pytest.mark.unit

TRAY_BLUE = (190, 110, 20)  # BGR, hue about 107 on OpenCV's scale
TABLE = (225, 225, 225)


def scene(gap_px: int) -> np.ndarray:
    """Two 60 x 80 px trays side by side on a grey table, gap_px apart, a dark cell in each."""
    im = np.full((120, 200, 3), TABLE, np.uint8)
    x0 = 20
    for k in range(2):
        x = x0 + k * (60 + gap_px)
        im[20:100, x : x + 60] = TRAY_BLUE
        im[40:50, x + 20 : x + 30] = (40, 40, 40)  # a cell or tag: a hole in the blue
    return im


def test_blue_mask_takes_tray_blue_not_table_or_dark():
    im = scene(10)
    m = trays.blue_mask(im)
    assert m[60, 40] and not m[5, 5] and not m[45, 45]


def test_trays_with_a_gap_are_two_shapes_with_holes_filled():
    shapes = trays.shapes_from_mask(trays.blue_mask(scene(6)), min_area_px=1000)
    assert len(shapes) == 2
    assert all(cv2.contourArea(c) > 0.95 * 59 * 79 for c in shapes)


def test_touching_trays_are_one_shape():
    assert len(trays.shapes_from_mask(trays.blue_mask(scene(0)), min_area_px=1000)) == 1


def test_small_blue_specks_are_not_shapes():
    im = np.full((50, 50, 3), TABLE, np.uint8)
    im[10:16, 10:16] = TRAY_BLUE
    assert trays.shapes_from_mask(trays.blue_mask(im), min_area_px=100) == []


def test_tag_heading_upright_and_turned():
    upright = [(0, 0), (10, 0), (10, 10), (0, 10)]  # top-left, top-right, bottom-right, bottom-left
    assert trays.tag_heading_deg(upright) == pytest.approx(0)
    turned = [(10, 10), (0, 10), (0, 0), (10, 0)]  # the same tag turned 180 degrees
    assert trays.tag_heading_deg(turned) == pytest.approx(180)
    east = [(10, 0), (10, 10), (0, 10), (0, 0)]  # top edge faces east (image right)
    assert trays.tag_heading_deg(east) == pytest.approx(90)


def test_tray_of_a1_edge_and_other_tags():
    assert trays.tray_of(5) == 5
    assert trays.tray_of(14) == 5  # 20 mm edge tag on tray 5
    assert trays.tray_of(200) is None


def test_judge_shape():
    assert trays.judge_shape([5, 14], 1.0) == ("one tray", [5])
    assert trays.judge_shape([5, 6], 1.0) == ("several trays", [5, 6])
    assert trays.judge_shape([], 1.0) == ("no tray", [])
    assert trays.judge_shape([5], 0.5) == ("part of a tray", [5])


def test_two_tray_shape_with_one_tag_is_merged():
    assert trays.judge_shape([5], 2.0) == ("several trays", [5])


def test_tags_in_shape_counts_tags_just_outside():
    c = np.array([[[0, 0]], [[50, 0]], [[50, 50]], [[0, 50]]], np.int32)
    tags = [{"id": 1, "cx": 25, "cy": 25}, {"id": 2, "cx": 54, "cy": 25}, {"id": 3, "cx": 80, "cy": 25}]
    assert trays.tags_in_shape(c, tags, near_px=5) == [1, 2]


def test_nearest_slots():
    slots = [{"name": "North 1", "centre": (0, 0)}, {"name": "North 2", "centre": (100, 0)}]
    name, d1, name2, d2 = trays.nearest_slots(30, 0, slots)
    assert (name, name2) == ("North 1", "North 2") and (d1, d2) == (30, 70)


def test_row_order_names_slots_by_row_then_west_to_east():
    import summarise

    pts = {i + 1: (100 * (6 - i % 6), 50 if i < 6 else 900) for i in range(12)}  # tray 1 is east
    slots = summarise.row_order(pts)
    assert slots[1] == "North 6" and slots[6] == "North 1" and slots[7] == "South 6"
    assert summarise.row_order({1: (0, 0)}) == {}


def session_file(tmp_path, trays_):
    """A made-up session: stills folder, record, step sets, steps where nothing moved, trays."""
    p = tmp_path / "s.json"
    p.write_text(json.dumps({
        "stills": "experiments/2026-10-19_abcd1234/stills/2026-10-19",
        "record": "experiments/round1/session-2026-10-19.csv",
        "sets": {"gaps": ["1", "2"], "touching": ["5", "6"]},
        "nothing_moved": ["1", "6"],
        "trays": trays_}))
    return p


def test_session_file_is_read_back(tmp_path):
    s = trays.load_session(session_file(tmp_path, [[13], [14], [15, 40]]))
    assert s.stills_dir == trays.RIG / "experiments/2026-10-19_abcd1234/stills/2026-10-19"
    assert s.record == trays.REPO / "experiments/round1/session-2026-10-19.csv"
    assert s.sets == {"gaps": ["1", "2"], "touching": ["5", "6"]}
    assert s.nothing_moved == {"1", "6"}
    assert s.trays == [13, 14, 15]  # each tray named by its first tag


def test_session_with_a_tag_listed_twice_is_refused(tmp_path):
    with pytest.raises(ValueError, match="13"):
        trays.load_session(session_file(tmp_path, [[13], [14, 13]]))


def test_tag_names_the_tray_of_its_own_session(tmp_path):
    s = trays.load_session(session_file(tmp_path, [[13], [14], [15, 40]]))
    assert trays.tray_of(13, s) == 13  # on 15 October tag 13 was tray 8's edge tag
    assert trays.tray_of(40, s) == 15
    assert trays.tray_of(4, s) is None  # a tag not in the table names no tray
