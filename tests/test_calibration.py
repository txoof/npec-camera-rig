import numpy as np
import pytest

from npec_rig.calibration import (
    CoverageResult,
    QuadrantCoverage,
    build_install_report,
    build_scale_field,
    build_uncertainty_field,
    describe_coverage,
    describe_regional_coverage,
    describe_scale_variation,
    holdout_coverage_test,
    refit_scale_factor,
    regional_coverage_test,
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


def test_regional_coverage_flags_an_empty_quadrant() -> None:
    # 3 tags each in top-right, bottom-left, bottom-right; none in top-left.
    positions = [
        (700, 100), (1000, 100), (700, 400),  # top-right
        (100, 700), (100, 1000), (400, 700),  # bottom-left
        (700, 700), (1000, 1000), (700, 1000),  # bottom-right
    ]
    detections = [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)]
    results = regional_coverage_test(
        detections, {i: 30.0 for i in range(len(positions))}, frame_width=1100, frame_height=1100
    )

    by_quadrant = {r.quadrant: r for r in results}
    assert by_quadrant["top-left"].observed_count == 0
    assert by_quadrant["top-left"].mean_abs_pct_error is None
    assert by_quadrant["bottom-right"].observed_count == 3


def test_regional_coverage_flags_a_quadrant_the_rest_of_the_field_predicts_badly() -> None:
    xs = (100, 400, 700, 1000)
    ys = (0, 333, 667, 1000)
    positions = [(x, y) for y in ys for x in xs]  # 16 points, matches _grid_positions()

    def ppm(x: float, y: float) -> float:
        # Flat everywhere except a scale anomaly confined to the bottom-right quadrant.
        return 4.5 if (x >= 550 and y >= 550) else 4.0

    size_mm = 30.0
    detections = [
        _square_detection(tag_id, x, y, ppm(x, y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ]
    results = regional_coverage_test(
        detections, {i: size_mm for i in range(len(positions))}, frame_width=1100, frame_height=1100
    )

    by_quadrant = {r.quadrant: r for r in results}
    bottom_right = by_quadrant["bottom-right"]
    assert bottom_right.observed_count == 4
    assert bottom_right.mean_abs_pct_error > 5.0


def test_regional_coverage_reports_none_when_too_little_data_to_fit() -> None:
    positions = [(700, 100), (100, 700), (700, 700)]  # one tag each in 3 quadrants, none top-left
    detections = [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)]
    results = regional_coverage_test(
        detections, {i: 30.0 for i in range(3)}, frame_width=1100, frame_height=1100
    )

    by_quadrant = {r.quadrant: r for r in results}
    assert by_quadrant["top-left"].observed_count == 0
    # top-right has 1 observed tag, but only 2 tags outside it -- not enough to fit a plane.
    assert by_quadrant["top-right"].observed_count == 1
    assert by_quadrant["top-right"].mean_abs_pct_error is None


def test_describe_regional_coverage_is_silent_when_all_quadrants_are_fine() -> None:
    results = (
        QuadrantCoverage("top-left", 4, 0.5, 1.0),
        QuadrantCoverage("top-right", 4, 0.8, 1.2),
        QuadrantCoverage("bottom-left", 4, 0.3, 0.9),
        QuadrantCoverage("bottom-right", 4, 0.6, 1.1),
    )
    assert describe_regional_coverage(results, threshold_pct=2.0) == []


def test_describe_regional_coverage_names_the_weak_and_empty_quadrants() -> None:
    results = (
        QuadrantCoverage("top-left", 0, None, None),
        QuadrantCoverage("top-right", 4, 0.8, 1.2),
        QuadrantCoverage("bottom-left", 4, 6.0, 9.0),
        QuadrantCoverage("bottom-right", 1, None, None),
    )
    lines = describe_regional_coverage(results, threshold_pct=2.0)
    assert any("top-left" in line and "add a sheet" in line for line in lines)
    assert any("bottom-left" in line and "6.0%" in line for line in lines)
    assert any("bottom-right" in line and "too little coverage" in line for line in lines)
    assert not any("top-right" in line for line in lines)


def test_install_report_includes_regional_coverage_lines_when_given() -> None:
    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ]
    sizes = {i: 30.0 for i in range(len(detections))}
    field = build_scale_field(detections, sizes)
    regional = regional_coverage_test(detections, sizes, frame_width=1100, frame_height=1100)

    report = build_install_report(field, positions, None, regional)
    assert report[0].startswith("Scale varies")
    # Whatever regional lines exist (there may be none, if coverage is even) come after.
    assert len(report) == 1 + len(describe_regional_coverage(regional))


def test_uncertainty_is_near_zero_when_the_plane_fits_perfectly() -> None:
    positions = _grid_positions()
    detections = [_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)]
    sizes = {i: 30.0 for i in range(len(positions))}
    field = build_scale_field(detections, sizes)

    uncertainty = build_uncertainty_field(field, detections, sizes)
    assert uncertainty.local_uncertainty_pct(500, 500, k=5) < 0.01
    assert uncertainty.local_uncertainty_pct(100, 0, k=3) < 0.01


def test_uncertainty_reflects_local_bias_even_when_neighbours_agree_with_each_other() -> None:
    # A local cluster all sharing the same 5% bias relative to the fitted plane: tight agreement
    # among themselves (std about their own mean ~= 0), but each one really is off by ~5%.
    # RMS-about-zero must report that as real uncertainty; std-about-the-neighbours'-mean would
    # hide it entirely -- the exact honesty-plot failure this field exists to avoid.
    size_mm = 30.0
    base_positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, 4.0 * size_mm) for tag_id, (x, y) in enumerate(base_positions)
    ]
    cluster = [(540, 540), (560, 540), (550, 560)]
    for i, (x, y) in enumerate(cluster):
        detections.append(_square_detection(100 + i, x, y, 4.0 * 1.05 * size_mm))
    sizes = {d.tag_id: size_mm for d in detections}

    field = build_scale_field(detections, sizes)
    uncertainty = build_uncertainty_field(field, detections, sizes)

    near_cluster = uncertainty.local_uncertainty_pct(550, 550, k=3)
    far_from_cluster = uncertainty.local_uncertainty_pct(100, 0, k=3)
    assert near_cluster > 3.0
    assert far_from_cluster < near_cluster


def test_uncertainty_field_raises_with_fewer_than_two_usable_tags() -> None:
    detections = [_square_detection(0, 100, 100, 120)]
    field = build_scale_field(
        [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())],
        {i: 30.0 for i in range(len(_grid_positions()))},
    )
    with pytest.raises(ValueError, match="at least 2"):
        build_uncertainty_field(field, detections, {0: 30.0})


def test_refit_scale_factor_recovers_a_uniform_change_keeping_shape() -> None:
    # A frozen field from a genuine tilted plane, built once (the paper calibration).
    size_mm = 30.0
    ppm_at_centre = 4.0

    def depth(y: float) -> float:
        return 1 + 0.1 * (y - 500) / 500

    def ppm(y: float) -> float:
        return ppm_at_centre / depth(y)

    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, ppm(y) * size_mm) for tag_id, (x, y) in enumerate(positions)
    ]
    frozen = build_scale_field(detections, {i: size_mm for i in range(len(positions))})

    # Refocus: everything is now uniformly 10% bigger. Only a few interior tray tags this time.
    k = 1.10
    interior_positions = [(400, 400), (700, 400), (400, 667), (700, 667)]
    tray_detections = [
        _square_detection(90 + i, x, y, k * ppm(y) * size_mm)
        for i, (x, y) in enumerate(interior_positions)
    ]
    refit = refit_scale_factor(frozen, tray_detections, {90 + i: size_mm for i in range(4)})

    assert refit.interior_scatter_pct == pytest.approx(0.0, abs=1e-6)
    assert refit.field._coeffs == frozen._coeffs  # shape untouched
    assert refit.field.residual_std_pct == frozen.residual_std_pct  # global diagnostic untouched
    # The refit field's scale, anywhere, is exactly k times the frozen field's -- shape preserved.
    for x, y in [(0, 0), (500, 500), (1000, 1000), (100, 900)]:
        assert refit.field.px_per_mm(x, y) == pytest.approx(k * frozen.px_per_mm(x, y), rel=1e-6)


def test_refit_scale_factor_reports_scatter_when_interior_tags_disagree() -> None:
    positions = _grid_positions()
    detections = [_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)]
    frozen = build_scale_field(detections, {i: 30.0 for i in range(len(positions))})

    # Interior tags that don't all imply the same scale factor.
    noisy = [
        _square_detection(90, 400, 400, 120),
        _square_detection(91, 700, 400, 132),  # 10% bigger
        _square_detection(92, 400, 667, 108),  # 10% smaller
    ]
    refit = refit_scale_factor(frozen, noisy, {90: 30.0, 91: 30.0, 92: 30.0})

    assert refit.interior_scatter_pct > 5.0
    assert refit.field._coeffs == frozen._coeffs


def test_refit_scale_factor_with_a_single_tag_has_zero_scatter() -> None:
    positions = _grid_positions()
    detections = [_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)]
    frozen = build_scale_field(detections, {i: 30.0 for i in range(len(positions))})

    refit = refit_scale_factor(frozen, [_square_detection(90, 500, 500, 130)], {90: 30.0})
    assert refit.interior_scatter_pct == 0.0


def test_refit_scale_factor_raises_with_no_usable_detections() -> None:
    positions = _grid_positions()
    detections = [_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)]
    frozen = build_scale_field(detections, {i: 30.0 for i in range(len(positions))})

    with pytest.raises(ValueError, match="at least 1"):
        refit_scale_factor(frozen, [_square_detection(999, 500, 500, 130)], {90: 30.0})


def test_calibration_artifact_round_trips_through_dict() -> None:
    from npec_rig.calibration import (
        CalibrationArtifact,
        calibration_artifact_from_dict,
        calibration_artifact_to_dict,
    )
    from npec_rig.tripwire import CornerBaseline

    field = build_scale_field(
        [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())],
        {i: 30.0 for i in range(len(_grid_positions()))},
    )
    baseline = CornerBaseline(
        corners_by_id={
            450: ((0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
            451: ((900.0, 0.0), (1000.0, 0.0), (1000.0, 100.0), (900.0, 100.0)),
        }
    )
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=field,
        corner_baseline=baseline,
        lens_position=6.3,
    )

    data = calibration_artifact_to_dict(artifact)
    assert data["version"] == 2
    restored = calibration_artifact_from_dict(data)

    assert restored == artifact


def test_calibration_artifact_without_a_baseline_round_trips() -> None:
    from npec_rig.calibration import CalibrationArtifact, calibration_artifact_from_dict, calibration_artifact_to_dict

    field = build_scale_field(
        [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())],
        {i: 30.0 for i in range(len(_grid_positions()))},
    )
    artifact = CalibrationArtifact(created_at="2026-09-20T12:00:00+00:00", scale_field=field)

    restored = calibration_artifact_from_dict(calibration_artifact_to_dict(artifact))
    assert restored == artifact
    assert restored.corner_baseline is None


def test_calibration_artifact_rejects_an_unsupported_version() -> None:
    from npec_rig.calibration import calibration_artifact_from_dict

    data = {
        "version": 99,
        "created_at": "2026-09-20T12:00:00+00:00",
        "scale_field": {"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": 4.0, "residual_std_pct": 0.0},
        "lens_position": None,
    }
    with pytest.raises(ValueError, match="unsupported calibration artifact version"):
        calibration_artifact_from_dict(data)


def test_build_calibration_report_assembles_pieces_from_one_set_of_detections() -> None:
    from npec_rig.calibration import build_calibration_report

    positions = _grid_positions()
    detections = [
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ]
    sizes = {i: 30.0 for i in range(len(detections))}

    report = build_calibration_report(detections, sizes, frame_width=1100, frame_height=1100)

    field = build_scale_field(detections, sizes)
    coverage = holdout_coverage_test(detections, sizes)
    regional = regional_coverage_test(detections, sizes, 1100, 1100)
    expected = build_install_report(field, positions, coverage, regional)
    assert report == expected


def test_build_calibration_report_skips_coverage_line_with_too_few_tags_for_a_holdout() -> None:
    from npec_rig.calibration import build_calibration_report

    positions = [(100, 100), (900, 100), (500, 900), (100, 900), (900, 900)]
    detections = [_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)]
    sizes = {i: 30.0 for i in range(len(positions))}

    report = build_calibration_report(detections, sizes, frame_width=1000, frame_height=1000)
    assert report[0].startswith("Scale varies")
    assert not any("Coverage sufficient" in line or "Coverage insufficient" in line for line in report)
