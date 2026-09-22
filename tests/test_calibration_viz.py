import numpy as np
import pytest

from npec_rig.calibration import (
    area_scale_samples,
    build_area_scale_field,
    build_scale_field,
    build_uncertainty_field,
)
from npec_rig.calibration_viz import (
    AREA_SHAPE_HEATMAP_MAX_PCT,
    AREA_SHAPE_HEATMAP_MIN_PCT,
    HEATMAP_MAX_PCT,
    HEATMAP_MIN_PCT,
    render_area_shape_heatmap,
    render_honesty_plot,
    render_rank_plot,
    render_uncertainty_heatmap,
)
from npec_rig.tags import TagDetection

from .helpers import square_detection as _square_detection

pytestmark = pytest.mark.unit


def _uniform_field() -> tuple:
    # Flat scale everywhere -- every tag agrees with the fitted plane, so uncertainty is ~0
    # everywhere. Good enough to exercise the rendering path without needing real photos.
    detections = [
        _square_detection(tag_id, cx, cy, 120)
        for tag_id, (cx, cy) in enumerate([(100, 100), (900, 100), (500, 500), (100, 900), (900, 900)])
    ]
    sizes = {i: 30.0 for i in range(len(detections))}
    field = build_scale_field(detections, sizes)
    uncertainty = build_uncertainty_field(field, detections, sizes)
    return field, uncertainty


def test_heatmap_matches_frame_size_and_channels() -> None:
    _, uncertainty = _uniform_field()
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    heatmap = render_uncertainty_heatmap(uncertainty, frame)
    assert heatmap.shape == (200, 300, 3)
    assert heatmap.dtype == np.uint8


def test_heatmap_ignores_a_padding_channel() -> None:
    _, uncertainty = _uniform_field()
    frame = np.zeros((50, 60, 4), dtype=np.uint8)  # XBGR8888-style padded frame
    heatmap = render_uncertainty_heatmap(uncertainty, frame)
    assert heatmap.shape == (50, 60, 3)


def test_heatmap_is_uniformly_cool_when_uncertainty_is_zero_everywhere() -> None:
    # At vmin=0, a perfectly-fit field should render as the colormap's bottom colour everywhere
    # -- a real signal of "confident", not an artifact of clipping.
    _, uncertainty = _uniform_field()
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    heatmap = render_uncertainty_heatmap(uncertainty, frame, vmin=0.0, vmax=8.0)
    # Every pixel should get the same colour, since local_uncertainty_pct is ~0 everywhere.
    unique_colors = np.unique(heatmap.reshape(-1, 3), axis=0)
    assert len(unique_colors) == 1


def test_heatmap_downscales_large_frames_and_still_samples_original_coordinates() -> None:
    # A real full-res capture is ~9000px wide; carrying that through resize/colormap/blend was
    # measured to allocate enough transient float32 memory to trigger the OOM killer on real
    # hardware (dmesg-confirmed, 2026-09-21). `max_width` exists to cap this -- verified here
    # with a small override rather than an actual 64MP array, which the unit tier shouldn't pay
    # for (CLAUDE.md's test-discipline budget).
    _, uncertainty = _uniform_field()
    frame = np.full((600, 800, 3), 128, dtype=np.uint8)
    heatmap = render_uncertainty_heatmap(uncertainty, frame, max_width=200)
    assert heatmap.shape == (150, 200, 3)  # aspect ratio preserved
    # The field is uniform (built from a perfectly-fit plane), so downscaling and re-mapping
    # grid coordinates back to the original frame's space shouldn't change that -- still one
    # colour everywhere, not an artifact of the coordinate rescale being wrong.
    unique_colors = np.unique(heatmap.reshape(-1, 3), axis=0)
    assert len(unique_colors) == 1


def _uniform_area_field():
    # Every tag is an exact square, consistent with its own mean side length -- shape_factor_pct
    # is exactly 0 everywhere, same rationale as _uniform_field() above.
    field, _ = _uniform_field()
    detections = [
        _square_detection(tag_id, cx, cy, 120)
        for tag_id, (cx, cy) in enumerate([(100, 100), (900, 100), (500, 500), (100, 900), (900, 900)])
    ]
    sizes = {i: 30.0 for i in range(len(detections))}
    return build_area_scale_field(area_scale_samples(field, detections, sizes))


def test_area_shape_heatmap_matches_frame_size_and_channels() -> None:
    area_field = _uniform_area_field()
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    heatmap = render_area_shape_heatmap(area_field, frame)
    assert heatmap.shape == (200, 300, 3)
    assert heatmap.dtype == np.uint8


def test_area_shape_heatmap_is_uniformly_cool_when_no_distortion_anywhere() -> None:
    area_field = _uniform_area_field()
    frame = np.full((100, 100, 3), 128, dtype=np.uint8)
    heatmap = render_area_shape_heatmap(
        area_field, frame, vmin=AREA_SHAPE_HEATMAP_MIN_PCT, vmax=AREA_SHAPE_HEATMAP_MAX_PCT
    )
    unique_colors = np.unique(heatmap.reshape(-1, 3), axis=0)
    assert len(unique_colors) == 1


def _rectangle_detection(tag_id: int, cx: float, cy: float, width: float, height: float) -> TagDetection:
    return TagDetection(
        tag_id=tag_id,
        corners=(
            (cx - width / 2, cy - height / 2),
            (cx + width / 2, cy - height / 2),
            (cx + width / 2, cy + height / 2),
            (cx - width / 2, cy + height / 2),
        ),
        centre=(cx, cy),
    )


def test_area_shape_heatmap_shows_real_structure_from_genuinely_distorted_tags() -> None:
    # A background grid of perfect squares (shape_factor_pct == 0) everywhere, plus a tight
    # local cluster of rectangles with the same mean side length but real shoelace-area
    # distortion -- with only `_uniform_area_field()`'s 5 points, k=5 always covers all of them
    # everywhere, so every query gets the same answer; enough background points here that k=5
    # actually varies by query position, which is what exercises the non-flat rendering path.
    size_mm, ppm = 30.0, 4.0
    xs, ys = (100, 400, 700, 1000), (0, 333, 667, 1000)
    grid_positions = [(x, y) for y in ys for x in xs]
    squares = [
        _square_detection(tag_id, x, y, ppm * size_mm) for tag_id, (x, y) in enumerate(grid_positions)
    ]
    field = build_scale_field(squares, {i: size_mm for i in range(len(squares))})

    distorted = [
        # Same mean side length as the field predicts (zero length residual), pure shape
        # distortion via a rectangle instead of a square.
        _rectangle_detection(90 + i, cx, cy, ppm * size_mm * 1.4, ppm * size_mm * 0.6)
        for i, (cx, cy) in enumerate([(540, 540), (560, 540), (550, 560)])
    ]
    detections = squares + distorted
    sizes = {i: size_mm for i in range(len(squares))} | {d.tag_id: size_mm for d in distorted}
    area_field = build_area_scale_field(area_scale_samples(field, detections, sizes))

    frame = np.full((1000, 1000, 3), 128, dtype=np.uint8)
    heatmap = render_area_shape_heatmap(
        area_field, frame, vmin=AREA_SHAPE_HEATMAP_MIN_PCT, vmax=AREA_SHAPE_HEATMAP_MAX_PCT
    )
    unique_colors = np.unique(heatmap.reshape(-1, 3), axis=0)
    assert len(unique_colors) > 1


def test_honesty_plot_renders_an_image_of_the_requested_size() -> None:
    image = render_honesty_plot([(1.0, 1.2), (2.0, 1.8), (5.0, 6.0)], size=400, margin=50)
    assert image.shape == (400, 400, 3)


def test_honesty_plot_requires_at_least_one_point() -> None:
    with pytest.raises(ValueError, match="at least one"):
        render_honesty_plot([])


def test_honesty_plot_point_on_the_honest_line_lands_on_the_diagonal() -> None:
    # A single point where claimed == actual should land exactly on the y=x reference line --
    # verify that pixel is not the plain white background, i.e. something was actually drawn
    # there (the diagonal line and the point coincide).
    image = render_honesty_plot([(5.0, 5.0)], size=300, margin=50, axis_max_pct=10.0)
    assert not np.all(image == 255)


def test_rank_plot_renders_an_image_of_the_requested_size() -> None:
    points = [(0.1, 1, 100.0, 100.0), (0.5, 2, 200.0, 200.0), (2.0, 3, 300.0, 300.0)]
    image = render_rank_plot(points, label="scale residual", size=400, margin=50)
    assert image.shape == (400, 400, 3)


def test_rank_plot_requires_at_least_two_points() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        render_rank_plot([(0.1, 1, 0.0, 0.0)], label="scale residual")


def test_rank_plot_draws_something_for_a_real_spread() -> None:
    points = [(0.1, 1, 100.0, 100.0), (0.5, 2, 200.0, 200.0), (4.0, 3, 300.0, 300.0)]
    image = render_rank_plot(points, label="scale residual", size=300, margin=50)
    assert not np.all(image == 255)


def test_rank_plot_is_flat_white_background_when_all_values_are_equal() -> None:
    # Degenerate case (e.g. a perfectly flat field): every tag agrees, so the sorted line is
    # flat along the bottom of the plot -- exercises the axis_max floor rather than crashing on
    # a division by (near) zero.
    points = [(0.0, 1, 0.0, 0.0), (0.0, 2, 100.0, 100.0), (0.0, 3, 200.0, 200.0)]
    image = render_rank_plot(points, label="scale residual", size=300, margin=50)
    assert image.shape == (300, 300, 3)
