import numpy as np
import pytest

from npec_rig.calibration import (
    CoverageResult,
    build_install_report,
    build_scale_field,
    describe_coverage,
    describe_scale_variation,
    holdout_coverage_test,
)

from .helpers import square_detection as _square_detection

pytestmark = pytest.mark.unit


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


def test_scale_variation_is_evaluated_over_the_tag_cloud_not_the_frame() -> None:
    # Tags only span x in [100, 900], y in [100, 900] -- a much smaller box than a real frame.
    # Depth (and so scale) varies with y only, over the *tag cloud's* extent.
    size_mm = 30.0
    ppm_at_centre = 4.0

    def ppm(y: float) -> float:
        depth = 1 + 0.2 * (y - 500) / 400
        return ppm_at_centre / depth

    positions = [(100, 100), (900, 100), (100, 900), (900, 900), (500, 500)]
    detections = [
        _square_detection(tag_id, x, y, ppm(y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ]
    field = build_scale_field(detections, {i: size_mm for i in range(len(detections))})

    line = describe_scale_variation(field, [(x, y) for x, y in positions])
    expected_variation = 100.0 * (ppm(100) - ppm(900)) / ((ppm(100) + ppm(900)) / 2)
    assert f"{expected_variation:.0f}%" in line
    assert "top" in line  # y=100 (top, in image coords) is where scale is largest here


def test_scale_variation_line_names_the_worst_corner() -> None:
    detections = [
        _square_detection(0, 0, 0, 100),
        _square_detection(1, 1000, 0, 100),
        _square_detection(2, 0, 1000, 100),
        _square_detection(3, 1000, 1000, 150),  # bottom-right: clearly the outlier
        _square_detection(4, 500, 500, 105),
    ]
    field = build_scale_field(detections, {i: 30.0 for i in range(5)})
    line = describe_scale_variation(field, [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)])
    assert "bottom-right" in line


def test_describe_coverage_reports_sufficient_under_threshold() -> None:
    coverage = CoverageResult(fit_count=8, held_out_count=8, mean_abs_pct_error=1.2, max_abs_pct_error=3.0)
    line = describe_coverage(coverage, threshold_pct=2.0)
    assert "sufficient" in line
    assert "insufficient" not in line


def test_describe_coverage_reports_insufficient_over_threshold() -> None:
    coverage = CoverageResult(fit_count=8, held_out_count=8, mean_abs_pct_error=5.0, max_abs_pct_error=9.0)
    line = describe_coverage(coverage, threshold_pct=2.0)
    assert "insufficient" in line


def test_install_report_includes_scale_line_and_coverage_when_given() -> None:
    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ]
    sizes = {i: 30.0 for i in range(len(detections))}
    field = build_scale_field(detections, sizes)
    coverage = holdout_coverage_test(detections, sizes)

    report = build_install_report(field, positions, coverage)
    assert len(report) == 2
    assert "Scale varies" in report[0]
    assert "Coverage" in report[1]


def test_install_report_omits_coverage_line_when_not_given() -> None:
    positions = [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)]
    detections = [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)]
    field = build_scale_field(detections, {i: 30.0 for i in range(5)})

    report = build_install_report(field, positions)
    assert len(report) == 1
