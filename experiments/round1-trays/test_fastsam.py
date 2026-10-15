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
    assert tiles[0]["x1"] - tiles[0]["x0"] == 1500 + int(1.5 * fastsam.TRAY_W_PX)


def test_tiles_need_twelve_a1_tags():
    assert fastsam.tiles_from_tags([{"id": 1, "cx": 0, "cy": 0}]) == []
