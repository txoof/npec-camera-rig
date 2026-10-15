import numpy as np
import pytest

import fastsam

pytestmark = pytest.mark.unit


def test_dfl_distances_picks_the_peak_bin():
    bins = np.full((1, 64), -20.0)
    for side, k in enumerate((3, 0, 15, 7)):
        bins[0, side * 16 + k] = 20.0
    assert fastsam.dfl_distances(bins)[0] == pytest.approx([3, 0, 15, 7], abs=1e-6)


def test_is_tray_mask():
    assert fastsam.is_tray_mask(1.0, 0.95, 305, 366)
    assert not fastsam.is_tray_mask(2.0, 0.95, 610, 366)  # two trays
    assert not fastsam.is_tray_mask(1.0, 0.95, 366, 305)  # landscape: not the 12-tray layout
    assert not fastsam.is_tray_mask(1.0, 0.6, 305, 366)  # ragged


def test_tiles_from_tags_two_trays_per_tile_in_rows():
    tags = [{"id": i + 1, "cx": 1000 + 1500 * (i % 6), "cy": 2000 if i < 6 else 5000} for i in range(12)]
    tiles = fastsam.tiles_from_tags(tags)
    assert [t["name"] for t in tiles] == ["North 1-2", "North 3-4", "North 5-6", "South 1-2", "South 3-4", "South 5-6"]
    assert tiles[0]["trays"] == [1, 2] and tiles[3]["trays"] == [7, 8]
    assert tiles[0]["x1"] - tiles[0]["x0"] == pytest.approx(1500 + 2 * fastsam.TILE_MARGIN * fastsam.TRAY_W_PX, abs=1)


def test_tiles_need_twelve_a1_tags():
    assert fastsam.tiles_from_tags([{"id": 1, "cx": 0, "cy": 0}]) == []


def square(x0, y0, side):
    return np.array([[[x0, y0]], [[x0 + side, y0]], [[x0 + side, y0 + side]], [[x0, y0 + side]]], np.int32)


def test_dedupe_keeps_best_filled_of_close_masks():
    a = {"cx": 0, "cy": 0, "fill": 0.9}
    b = {"cx": 10, "cy": 0, "fill": 0.95}
    c = {"cx": 500, "cy": 0, "fill": 0.9}
    assert fastsam.dedupe([a, b, c], same_px=100) == [b, c]


def test_link_tags_nearest_within_limit_and_clear_of_second():
    masks = [{"contour": square(0, 0, 100)}, {"contour": square(100, 0, 100)}]
    tags = [{"id": 5, "cx": 95, "cy": 120},  # 20 below mask 0, 20.6 from mask 1: too close to call
            {"id": 6, "cx": 150, "cy": 150},  # inside mask 1
            {"id": 7, "cx": 20, "cy": 150},  # 50 below mask 0, 94 from mask 1
            {"id": 8, "cx": 50, "cy": 300},  # 200 away: no link
            {"id": 400, "cx": 50, "cy": 50}]  # not a tray tag
    links, ambiguous = fastsam.link_tags(masks, tags, ppm=1.0)
    assert links == {6: 1, 7: 0} and ambiguous == [5]


def test_grid_tiles_overlap_so_every_tray_fits_one_tile():
    tiles = fastsam.grid_tiles(9152, 6944, 800, 6200)
    tray_w, tray_h = 1950, 1950  # tray with lip margin
    assert all(t["x1"] - t["x0"] == fastsam.GRID_TILE_PX for t in tiles)
    assert max(t["x1"] for t in tiles) == 9152 and min(t["x0"] for t in tiles) == 0
    for x in range(0, 9152 - tray_w, 97):
        for y in range(800, 6200 - tray_h, 97):
            assert any(t["x0"] <= x and x + tray_w <= t["x1"] and t["y0"] <= y and y + tray_h <= t["y1"]
                       for t in tiles), (x, y)


def test_window_starts_hold_any_item_wholly():
    lo, hi, size, item = 1000, 5100, 2600, 1950
    starts = fastsam.window_starts(lo, hi, size, item)
    assert starts[0] == lo and starts[-1] == hi - size
    for x in range(lo, hi - item + 1, 13):
        assert any(s <= x and x + item <= s + size for s in starts), x


def test_fallback_windows_cover_the_tray_at_either_corner():
    cx, cy = 5000, 3000
    win = fastsam.fallback_windows(cx, cy, 9152, 6944)
    bw, bh = fastsam.TRAY_BOX_PX
    # tag at the south-west corner (tray north-east of it) or the north-east corner (tray south-west)
    for x0, y0 in ((cx - 60, cy - bh + 60), (cx - bw + 60, cy - 60)):
        assert any(t["x0"] <= x0 and x0 + bw <= t["x1"] and t["y0"] <= y0 and y0 + bh <= t["y1"] for t in win)
