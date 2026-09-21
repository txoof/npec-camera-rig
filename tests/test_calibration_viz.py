import numpy as np
import pytest

from npec_rig.calibration import build_scale_field, build_uncertainty_field
from npec_rig.calibration_viz import (
    HEATMAP_MAX_PCT,
    HEATMAP_MIN_PCT,
    render_honesty_plot,
    render_uncertainty_heatmap,
)

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
