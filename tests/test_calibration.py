import numpy as np
import pytest

from npec_rig.calibration import build_scale_field, holdout_coverage_test
from npec_rig.tags import TagDetection

pytestmark = pytest.mark.unit


def _square_detection(tag_id: int, cx: float, cy: float, side_px: float) -> TagDetection:
    """A synthetic axis-aligned tag of exact known pixel size, centred at (cx, cy)."""
    half = side_px / 2
    corners = (
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    )
    return TagDetection(tag_id=tag_id, corners=corners, centre=(cx, cy))


def test_uniform_scale_is_recovered_everywhere() -> None:
    # No tilt: every 30mm tag is exactly 120px, wherever it sits in the frame.
    true_px_per_mm = 120 / 30
    detections = [
        _square_detection(tag_id, cx, cy, 120)
        for tag_id, (cx, cy) in enumerate([(100, 100), (900, 100), (500, 500), (100, 900)])
    ]
    field = build_scale_field(detections, {i: 30.0 for i in range(len(detections))})

    assert field.px_per_mm(500, 500) == pytest.approx(true_px_per_mm, rel=1e-6)
    assert field.px_per_mm(100, 900) == pytest.approx(true_px_per_mm, rel=1e-6)
    assert field.residual_std_pct == pytest.approx(0.0, abs=1e-6)


def test_known_linear_tilt_is_recovered() -> None:
    # A camera tilted relative to the table: depth D varies linearly with y (the model's fitted
    # quantity is relative depth, ~D), and scale ppm = k/D follows -- +/-10% in D over y in
    # [0, 1000], flat in x.
    size_mm = 30.0
    ppm_at_centre = 4.0

    def depth(y: float) -> float:
        return 1 + 0.1 * (y - 500) / 500

    def ppm(y: float) -> float:
        return ppm_at_centre / depth(y)

    positions = [(100, 0), (900, 0), (100, 500), (900, 500), (100, 1000), (900, 1000)]
    detections = [
        _square_detection(tag_id, cx, cy, ppm(cy) * size_mm)
        for tag_id, (cx, cy) in enumerate(positions)
    ]
    field = build_scale_field(detections, {i: size_mm for i in range(len(detections))})

    assert field.px_per_mm(500, 0) == pytest.approx(ppm(0), rel=1e-6)
    assert field.px_per_mm(500, 1000) == pytest.approx(ppm(1000), rel=1e-6)
    # Depth genuinely linear in y is exactly what the plane model fits -- residual ~0.
    assert field.residual_std_pct == pytest.approx(0.0, abs=1e-6)


def test_tags_without_a_known_size_are_ignored() -> None:
    detections = [
        _square_detection(0, 100, 100, 120),
        _square_detection(1, 900, 100, 120),
        _square_detection(2, 500, 900, 120),
        _square_detection(75, 500, 500, 200),  # a corner tag, deliberately not in the size map
    ]
    field = build_scale_field(detections, {0: 30.0, 1: 30.0, 2: 30.0})

    assert field.px_per_mm(500, 500) == pytest.approx(120 / 30, rel=1e-6)


def test_raises_with_fewer_than_three_usable_tags() -> None:
    detections = [
        _square_detection(0, 100, 100, 120),
        _square_detection(1, 900, 100, 120),
    ]
    with pytest.raises(ValueError, match="at least 3"):
        build_scale_field(detections, {0: 30.0, 1: 30.0})


def _grid_positions() -> list[tuple[float, float]]:
    xs = (100, 400, 700, 1000)
    ys = (0, 333, 667, 1000)
    return [(x, y) for y in ys for x in xs]  # 16 points


def test_holdout_error_is_near_zero_when_a_plane_truly_fits() -> None:
    size_mm = 30.0
    ppm_at_centre = 4.0

    def ppm(x: float, y: float) -> float:
        depth = 1 + 0.1 * (y - 500) / 500  # flat in x, linear in y -- a true plane
        return ppm_at_centre / depth

    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, ppm(x, y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ]
    result = holdout_coverage_test(detections, {i: size_mm for i in range(len(detections))})

    assert result.fit_count == 8
    assert result.held_out_count == 8
    assert result.mean_abs_pct_error < 0.01
    assert result.max_abs_pct_error < 0.01


def test_holdout_error_is_larger_when_the_surface_is_not_a_plane() -> None:
    size_mm = 30.0
    ppm_at_centre = 4.0

    def ppm(x: float, y: float) -> float:
        # A wobble in x on top of the y tilt -- not representable by a single plane.
        depth = 1 + 0.1 * (y - 500) / 500 + 0.08 * np.sin(x / 150)
        return ppm_at_centre / depth

    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, ppm(x, y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ]
    result = holdout_coverage_test(detections, {i: size_mm for i in range(len(detections))})

    assert result.mean_abs_pct_error > 0.5


def test_holdout_is_reproducible_with_the_same_seed() -> None:
    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ]
    sizes = {i: 30.0 for i in range(len(detections))}

    first = holdout_coverage_test(detections, sizes, seed=7)
    second = holdout_coverage_test(detections, sizes, seed=7)
    assert first == second


def test_raises_with_fewer_than_six_usable_tags() -> None:
    detections = [_square_detection(i, 100 * i, 100, 120) for i in range(5)]
    with pytest.raises(ValueError, match="at least 6"):
        holdout_coverage_test(detections, {i: 30.0 for i in range(5)})
