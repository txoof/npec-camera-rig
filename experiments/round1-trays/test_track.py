import pytest

import track

pytestmark = pytest.mark.unit

PPM = 5.0  # px per mm


def mask(trays_, verdict, cx=1000, cy=1000, ew=300, ns=360):
    return {"trays": " ".join(map(str, trays_)), "verdict": verdict, "cx_full": cx, "cy_full": cy,
            "ew_mm": ew, "ns_mm": ns}


def tag(x, y):
    return {"cx": x, "cy": y}


def test_heading_change_wraps_round():
    assert track.heading_change(356, 2) == 6
    assert track.heading_change(1, 180.5) == 179.5


def test_distance_uses_scale_at_midpoint():
    assert track.distance_mm((0, 0), (300, 400), lambda x, y: 5.0) == 100


def test_in_box_allows_the_tag_tolerance_past_the_edge():
    m = mask([1], "one tray")  # half widths 150 x 180 mm, box edge at x = 1000 + 750 px
    assert track.in_box(m, 1000 + 160 * PPM, 1000, PPM)  # 10 mm past the edge
    assert not track.in_box(m, 1000 + 170 * PPM, 1000, PPM)  # 20 mm past


def test_patch2_keeps_the_tray_whose_tag_is_inside():
    m = mask([3, 4], "several trays")
    tags = {3: [tag(1000 - 140 * PPM, 1000 + 170 * PPM)], 4: [tag(1000 + 200 * PPM, 1000)]}
    assert track.patch_two_tray_mask(m, tags, PPM) == (3, 4)


def test_patch2_leaves_a_mask_with_both_tags_inside():
    m = mask([3, 4], "several trays")
    tags = {3: [tag(900, 1000)], 4: [tag(1100, 1000)]}
    assert track.patch_two_tray_mask(m, tags, PPM) is None


def test_moves_judged_against_the_tag_unless_it_turned():
    assert track.classify_moves(120, 118, 2)["verdict"] == "move found"
    assert track.classify_moves(3, 118, 2)["verdict"] == "move missed"
    assert track.classify_moves(80, 2, 1)["verdict"] == "false move"
    assert track.classify_moves(2, 1, 1)["verdict"] == "still, agreed"
    assert track.classify_moves(5, 470, 179)["verdict"] == "not judged"
    assert track.classify_moves(None, 1, 1)["verdict"] == "not judged"


def test_resolve_still_patch2_then_elimination():
    far = 1000 + 400 * PPM
    masks = [mask([1], "one tray", cx=0), mask([2, 3], "several trays"), mask([], "no tray", cx=far)]
    tags = {1: [tag(0, 1000)], 2: [tag(1000, 1000)], 3: [tag(1000 + 200 * PPM, 1000)]}
    out = track.resolve_still(masks, tags, PPM)
    assert out[1]["label"] == track.MEASURED
    assert out[2]["label"] == track.PATCH2
    assert out[3]["label"] == track.ELIMINATION and out[3]["was"] == track.UNRESOLVED


def test_fill_gaps_fills_a_short_gap_inside_one_step():
    good = [True, False, False, True]
    assert track.fill_gaps(good, [not g for g in good], ["R3"] * 4) == [(1, 3)]


def test_fill_gaps_refuses_long_gaps_ends_and_step_boundaries():
    g = lambda s: [c == "g" for c in s]
    n = lambda s: [c == "n" for c in s]
    assert track.fill_gaps(g("gnnnng"), n("gnnnng"), ["R3"] * 6) == []  # 4 stills
    assert track.fill_gaps(g("nng"), n("nng"), ["R3"] * 3) == []  # sequence start
    assert track.fill_gaps(g("gnn"), n("gnn"), ["R3"] * 3) == []  # sequence end
    assert track.fill_gaps(g("gng"), n("gng"), ["4", "4", "6"]) == []  # across a boundary


def test_fill_gaps_needs_good_stills_on_both_sides():
    good = [True, False, False, True]  # a still kept by a patch is neither good nor needing
    need = [False, True, False, False]
    assert track.fill_gaps(good, need, ["R3"] * 4) == []


def test_spread_counts_trays_outside_1_to_12():
    rows = [{"step": "1", "tray": 13, "x_mm": 0, "y_mm": 0}, {"step": "1", "tray": 13, "x_mm": 6, "y_mm": 8}]
    n, rms, worst = track.spread(rows, lambda r: True, steps={"1"})["1"]
    assert (n, rms, worst) == (2, 5.0, 5.0)  # both 5 mm from their mean (3, 4)


class Scale:
    px_per_mm = staticmethod(lambda x, y: PPM)


def test_wrong_position_found_on_a_tray_outside_1_to_12():
    pos = [(0, 0), (0, 0), (1000, 0)]  # the third is 200 mm from the median at 5 px per mm
    rows = [{"order": k, "step": "1", "tray": 13, "label": track.MEASURED, "x_px": x, "y_px": y}
            for k, (x, y) in enumerate(pos)]
    stills = [{"scale": Scale()}] * 3
    assert track.off_positions(rows, stills, steps={"1"}) == {(2, 13): 200.0}


def test_gap_filled_on_a_tray_outside_1_to_12():
    def row(x):
        return {"label": track.MEASURED if x is not None else track.NO_MASK, "x_px": x, "y_px": None if x is None else 0,
                "off_median_mm": None, "heading_deg": 0.0}
    by = {k: {13: row(x)} for k, x in enumerate((0, None, 10))}
    stills = [{"still": f"s{k}", "step": "6", "scale": Scale()} for k in range(3)]
    track.patch3(by, stills, {f"s{k}": [] for k in range(3)})
    assert by[1][13]["label"] == track.FILLED and by[1][13]["x_px"] == 5  # midway, 1 mm from each
