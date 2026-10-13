import numpy as np
import pytest

from npec_rig.calibration import build_table_frame
from npec_rig.calibration_viz import (
    radial_fit,
    TAG_MAP_CANVAS_DIM,
    TAG_MAP_FAR_PCT,
    TAG_MAP_HEADER_PX,
    TAG_MAP_HISTOGRAM_PX,
    TAG_MAP_LARGE_COLOUR,
    TAG_MAP_NEUTRAL_COLOUR,
    TAG_MAP_RANGE_PCT,
    TAG_MAP_SMALL_COLOUR,
    render_level_overlay,
    render_radial_residual_plot,
    render_tag_map,
    tag_map_colour,
)
from npec_rig.tripwire import CornerBaseline, corner_level_readings

from .helpers import square_detection as _square_detection

def _axis_aligned_table_frame(size: float = 1000.0):
    """A `TableFrame` whose 4 corner tags sit exactly at an axis-aligned square's corners, so
    `to_fraction(x, y) == (x / size, y / size)` exactly -- a known, simple mapping to check
    rendering geometry against without depending on `build_table_frame`'s own correctness (that's
    `test_calibration.py`'s job).
    """
    baseline = CornerBaseline(
        corners_by_id={
            450: _square_detection(450, 0.0, 0.0, 20.0).corners,
            451: _square_detection(451, size, 0.0, 20.0).corners,
            452: _square_detection(452, size, size, 20.0).corners,
            455: _square_detection(455, 0.0, size, 20.0).corners,
        }
    )
    return build_table_frame(baseline)

pytestmark = pytest.mark.unit



pytestmark = pytest.mark.unit


def test_level_overlay_matches_frame_size_and_channels() -> None:
    frame = np.full((200, 300, 3), 128, dtype=np.uint8)
    detections = [
        _square_detection(450, 50.0, 50.0, 40),
        _square_detection(451, 250.0, 50.0, 40),
        _square_detection(452, 50.0, 150.0, 40),
    ]
    readings = corner_level_readings(detections)
    image = render_level_overlay(frame, readings)
    assert image.shape == (200, 300, 3)
    assert image.dtype == np.uint8


def test_level_overlay_draws_something_distinct_from_a_blank_frame() -> None:
    frame = np.full((200, 300, 3), 128, dtype=np.uint8)
    detections = [
        _square_detection(450, 50.0, 50.0, 40),
        _square_detection(451, 250.0, 50.0, 55),  # notably bigger -- closer
    ]
    readings = corner_level_readings(detections)
    image = render_level_overlay(frame, readings)
    assert not np.all(image == 128)


def test_level_overlay_handles_no_readings_without_crashing() -> None:
    frame = np.full((200, 300, 3), 128, dtype=np.uint8)
    image = render_level_overlay(frame, [])
    assert image.shape == (200, 300, 3)
    assert not np.all(image == 128)  # the "need more tags" caption still draws


def test_level_overlay_downscales_large_frames() -> None:
    frame = np.full((600, 800, 3), 128, dtype=np.uint8)
    detections = [
        _square_detection(450, 100.0, 100.0, 80),
        _square_detection(451, 700.0, 500.0, 80),
    ]
    readings = corner_level_readings(detections)
    image = render_level_overlay(frame, readings, max_width=200)
    assert image.shape == (150, 200, 3)  # aspect ratio preserved


def test_radial_plot_renders_an_image_of_the_requested_size() -> None:
    points = [(0.0, 0.1, 1), (100.0, 0.5, 2), (200.0, -0.3, 3), (300.0, 1.2, 4)]
    image = render_radial_residual_plot(points, label="scale residual", size=400, margin=50, top_margin=80)
    assert image.shape == (400, 400, 3)


def test_radial_plot_requires_at_least_two_points() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        render_radial_residual_plot([(0.0, 0.1, 1)], label="scale residual")


def test_radial_plot_draws_something_for_a_real_spread() -> None:
    points = [(0.0, 0.1, 1), (100.0, 0.5, 2), (200.0, -0.3, 3), (300.0, 1.2, 4)]
    image = render_radial_residual_plot(points, label="scale residual", size=300, margin=50, top_margin=80)
    assert not np.all(image == 255)


def test_radial_plot_handles_zero_variance_without_crashing() -> None:
    # Every tag has the exact same residual -- ss_tot is zero, which would divide by zero in a
    # naive R^2 calculation. Exercises the guard rather than the maths.
    points = [(0.0, 1.0, 1), (100.0, 1.0, 2), (200.0, 1.0, 3)]
    image = render_radial_residual_plot(points, label="scale residual", size=300, margin=50, top_margin=80)
    assert image.shape == (300, 300, 3)


def _tag(cx: float, cy: float, deviation: float, side: float = 60.0) -> tuple[np.ndarray, float]:
    return np.asarray(_square_detection(0, cx, cy, side).corners, dtype=float), deviation


def _canvas_px(table_px: float) -> int:
    """Where a full-resolution position on `_axis_aligned_table_frame()` lands on the map, for
    tags well inside the corner tags: the map adds a 2% margin on every side."""
    return int(round((table_px / 1000 + 0.02) / 1.04 * TAG_MAP_CANVAS_DIM))


def test_tag_map_colour_is_neutral_at_zero_and_saturates_at_the_range() -> None:
    assert tag_map_colour(0.0) == TAG_MAP_NEUTRAL_COLOUR
    assert tag_map_colour(-TAG_MAP_RANGE_PCT) == TAG_MAP_SMALL_COLOUR
    assert tag_map_colour(TAG_MAP_RANGE_PCT) == TAG_MAP_LARGE_COLOUR
    assert tag_map_colour(-10 * TAG_MAP_RANGE_PCT) == TAG_MAP_SMALL_COLOUR


def test_tag_map_stacks_header_square_map_and_histogram_when_not_to_scale() -> None:
    frame = np.full((500, 500, 3), 128, dtype=np.uint8)  # a 1000 px table reduced by half
    image = render_tag_map(frame, 0.5, _axis_aligned_table_frame(), [_tag(500, 500, 0.0)])
    assert image.shape == (
        TAG_MAP_HEADER_PX + TAG_MAP_CANVAS_DIM + TAG_MAP_HISTOGRAM_PX, TAG_MAP_CANVAS_DIM, 3
    )
    assert image.dtype == np.uint8


def test_tag_map_takes_the_corner_tags_photographed_proportions() -> None:
    # Corner tags twice as far apart across as down the photo: the map is half as tall as wide.
    baseline = CornerBaseline(
        corners_by_id={
            450: _square_detection(450, 0.0, 0.0, 20.0).corners,
            451: _square_detection(451, 1000.0, 0.0, 20.0).corners,
            452: _square_detection(452, 1000.0, 500.0, 20.0).corners,
            455: _square_detection(455, 0.0, 500.0, 20.0).corners,
        }
    )
    frame = np.full((250, 500, 3), 128, dtype=np.uint8)
    image = render_tag_map(frame, 0.5, build_table_frame(baseline), [_tag(500, 250, 0.0)])
    assert image.shape[1] == TAG_MAP_CANVAS_DIM
    assert image.shape[0] == TAG_MAP_HEADER_PX + TAG_MAP_CANVAS_DIM // 2 + TAG_MAP_HISTOGRAM_PX


def test_tag_map_fills_each_tag_with_its_colour_and_leaves_the_rest_grey() -> None:
    frame = np.full((500, 500, 3), 200, dtype=np.uint8)
    image = render_tag_map(
        frame, 0.5, _axis_aligned_table_frame(), [_tag(250, 250, -TAG_MAP_RANGE_PCT), _tag(750, 750, 0.4)]
    )
    canvas = image[TAG_MAP_HEADER_PX:TAG_MAP_HEADER_PX + TAG_MAP_CANVAS_DIM]
    small = canvas[_canvas_px(250 - 20), _canvas_px(250 - 20)]  # off centre: a far tag carries a sign there
    assert tuple(int(c) for c in small) == TAG_MAP_SMALL_COLOUR
    between = canvas[_canvas_px(500), _canvas_px(500)]
    assert between[0] == between[1] == between[2] == 100  # greyed photo, nothing painted between tags


def test_tag_map_outlines_only_tags_past_the_far_line() -> None:
    frame = np.full((500, 500, 3), 200, dtype=np.uint8)
    far = render_tag_map(frame, 0.5, _axis_aligned_table_frame(), [_tag(500, 500, TAG_MAP_FAR_PCT + 0.1)])
    near = render_tag_map(frame, 0.5, _axis_aligned_table_frame(), [_tag(500, 500, TAG_MAP_FAR_PCT - 0.1)])
    edge_y = TAG_MAP_HEADER_PX + _canvas_px(500 - 30)
    edge_x = _canvas_px(500)
    assert tuple(int(c) for c in far[edge_y, edge_x]) == (0, 0, 0)
    assert tuple(int(c) for c in near[edge_y, edge_x]) != (0, 0, 0)


def test_tag_map_widens_to_show_tags_outside_the_corner_tags() -> None:
    frame = np.full((600, 600, 3), 200, dtype=np.uint8)
    inside = render_tag_map(frame, 0.5, _axis_aligned_table_frame(), [_tag(500, 500, 0.0)])
    outside = render_tag_map(frame, 0.5, _axis_aligned_table_frame(), [_tag(1150, 500, 0.0)])
    # The map keeps its 900 px width; taking in a tag 15% past the right corner tags makes it
    # relatively shorter.
    assert outside.shape[1] == inside.shape[1] == TAG_MAP_CANVAS_DIM
    assert outside.shape[0] < inside.shape[0]


def test_tag_map_histogram_counts_tags_beyond_the_range_in_their_own_bars() -> None:
    frame = np.full((500, 500, 3), 200, dtype=np.uint8)
    tags = [_tag(200 + 100 * i, 500, d) for i, d in enumerate([-5.0, -0.1, 0.0, 0.1, 5.0])]
    image = render_tag_map(frame, 0.5, _axis_aligned_table_frame(), tags)
    histogram = image[-TAG_MAP_HISTOGRAM_PX:]
    # The two "beyond" bars, first and last, are drawn in the saturated colours.
    colours = {tuple(int(c) for c in px) for px in histogram.reshape(-1, 3)}
    assert TAG_MAP_SMALL_COLOUR in colours
    assert TAG_MAP_LARGE_COLOUR in colours


def test_radial_fit_finds_a_straight_line_exactly() -> None:
    points = [(r, 0.002 * r - 1.0, i) for i, r in enumerate((0.0, 500.0, 1000.0, 2000.0))]
    slope, intercept, r_squared = radial_fit(points)
    assert slope == pytest.approx(0.002)
    assert intercept == pytest.approx(-1.0)
    assert r_squared == pytest.approx(1.0)


def test_radial_fit_of_equal_values_has_r_squared_zero() -> None:
    assert radial_fit([(0.0, 0.5, 1), (100.0, 0.5, 2), (200.0, 0.5, 3)])[2] == 0.0
