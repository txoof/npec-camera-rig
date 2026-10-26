import inspect

import numpy as np
import pytest

from npec_rig.calibration import (
    sheet_layout,
    AreaScaleSample,
    CoverageResult,
    QuadrantCoverage,
    ScaleField,
    area_scale_samples,
    build_install_report,
    build_calibration_report,
    build_scale_field,
    build_table_frame,
    describe_area_scale_shape,
    describe_coplanarity,
    describe_coverage,
    describe_regional_coverage,
    describe_scale_variation,
    holdout_coverage_test,
    regional_coverage_test,
    scale_residual_samples,
)
from npec_rig.tags import TagDetection, tag_side_px
from npec_rig.tripwire import CornerBaseline

from .helpers import printed_sheet, printed_tag, rotate_detection
from .helpers import square_detection as _square_detection

pytestmark = pytest.mark.unit

_LAYOUT = sheet_layout()
_SIZES = {tag_id: 30.0 for tag_id in _LAYOUT}
# Neighbouring tags of one printed row (37.5 mm apart as printed), each pair used once.
_PAIRS = [
    (a, a + 1)
    for a in sorted(_LAYOUT)
    if a + 1 in _LAYOUT and _LAYOUT[a][0] == _LAYOUT[a + 1][0] and _LAYOUT[a + 1][1] - _LAYOUT[a][1] == 37.5
][::2]


def _paired(singles: list[TagDetection]) -> list[TagDetection]:
    """Each single test tag replaced by a printed pair of tags centred on it, as wide as it and
    spaced as printed at its scale (side / 30 px/mm): the pair's tag spacing gives the scale the
    single tag's edges used to give, at the same point. Pair k comes from the single tag's ID and
    is turned by 37 degrees times k, so that pairs laid on a regular grid never line up the way
    the print layout puts two tags of one page."""
    out = []
    for single in singles:
        side = tag_side_px(single.corners)
        a, b = _PAIRS[single.tag_id % len(_PAIRS)]
        half_gap = 37.5 / 2 * side / 30.0
        cx, cy = single.centre
        angle = 37.0 * single.tag_id
        out += [
            rotate_detection(printed_tag(a, cx - half_gap, cy, side), (cx, cy), angle),
            rotate_detection(printed_tag(b, cx + half_gap, cy, side), (cx, cy), angle),
        ]
    return out


def test_scale_comes_from_tag_spacing_not_tag_edges() -> None:
    # Test point 1 (#286): centres at exactly 5.0 px/mm as printed, every tag edge drawn 2% short.
    # Tag edges would give 4.90.
    detections = printed_sheet(2, 1000, 3000, 5.0, edge_scale=0.98)
    field = build_scale_field(detections, {d.tag_id: 30.0 for d in detections})

    assert field.px_per_mm(1500, 2300) == pytest.approx(5.00, rel=1e-6)


def test_scale_from_tag_spacing_follows_the_tilt_across_the_table() -> None:
    # Test point 2 (#286): two tag sheets at opposite ends of the frame, 4.9 and 5.1 px/mm by tag
    # spacing, both with tag edges 2% short. Half way, the plane in relative depth gives 1 / the
    # mean of 1/4.9 and 1/5.1 = 4.998.
    near = printed_sheet(2, 500, 3000, 4.9, edge_scale=0.98)
    far = printed_sheet(2, 7500, 3000, 5.1, edge_scale=0.98)
    detections = near + far
    field = build_scale_field(detections, {d.tag_id: 30.0 for d in detections})

    assert field.px_per_mm(500 + 105 * 4.9, 3000 - 150 * 4.9) == pytest.approx(4.90, abs=0.01)
    assert field.px_per_mm(7500 + 105 * 5.1, 3000 - 150 * 5.1) == pytest.approx(5.10, abs=0.01)
    half_way = (500 + 105 * 4.9 + 7500 + 105 * 5.1) / 2
    assert field.px_per_mm(half_way, 3000 - 150 * 5.0) == pytest.approx(4.998, abs=0.005)


def test_two_copies_of_one_page_side_by_side_are_not_paired_across() -> None:
    # Test point 4 (#286): two copies of page 2 touching (the second 160 mm to the right, 10 mm
    # between their nearest tags), both at exactly 5.0 px/mm. A tag paired with its partner on
    # the other copy would give a far wrong scale.
    detections = printed_sheet(2, 1000, 3000, 5.0) + printed_sheet(2, 1000 + 160 * 5.0, 3000, 5.0)
    field = build_scale_field(detections, {d.tag_id: 30.0 for d in detections})

    assert field.px_per_mm(1500, 2300) == pytest.approx(5.00, rel=1e-6)
    assert field.px_per_mm(2300, 2300) == pytest.approx(5.00, rel=1e-6)


def test_tags_more_than_90_mm_apart_are_not_paired() -> None:
    # Test point 4 (#286): a full page 2 at 5.0 px/mm, and far from it a second copy with only two
    # tags, 325 and 329 (150 mm apart as printed), drawn at 6.0 px/mm. Paired, they would pull the
    # fit away from 5.0; over 90 mm apart they are not used.
    sheet = printed_sheet(2, 1000, 3000, 5.0)
    stray = [d for d in printed_sheet(2, 5000, 6000, 6.0) if d.tag_id in (325, 329)]
    detections = sheet + stray
    field = build_scale_field(detections, {d.tag_id: 30.0 for d in detections})

    assert field.px_per_mm(1500, 2300) == pytest.approx(5.00, rel=1e-6)
    assert field.px_per_mm(5500, 5000) == pytest.approx(5.00, rel=1e-6)


def test_coverage_is_judged_from_tag_spacing_not_tag_edges() -> None:
    # Test point 6 (#286): four tag sheets at exactly 5.0 px/mm by tag spacing, their tag edges
    # short by different amounts (5% and 0% in a checkerboard, as sheets differ in real photos).
    # Judged by tag edges the holdout error would exceed the 2% target; by tag spacing it is 0.
    detections = [
        d
        for page, (x0, y0), edge_scale in (
            (2, (500, 2000), 0.95), (3, (6500, 2000), 1.0), (4, (500, 6000), 1.0), (5, (6500, 6000), 0.95)
        )
        for d in printed_sheet(page, x0, y0, 5.0, edge_scale=edge_scale)
    ]
    report = build_calibration_report(detections, {d.tag_id: 30.0 for d in detections}, 9152, 6944)

    assert "Coverage sufficient: holdout error 0.0% (target 2%)." in report


def test_uniform_scale_is_recovered_everywhere() -> None:
    # No tilt: every 30mm tag is exactly 120px, wherever it sits in the frame.
    true_px_per_mm = 120 / 30
    detections = _paired([
        _square_detection(tag_id, cx, cy, 120)
        for tag_id, (cx, cy) in enumerate([(100, 100), (900, 100), (500, 500), (100, 900)])
    ])
    field = build_scale_field(detections, _SIZES)

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
    detections = _paired([
        _square_detection(tag_id, cx, cy, ppm(cy) * size_mm)
        for tag_id, (cx, cy) in enumerate(positions)
    ])
    field = build_scale_field(detections, _SIZES)

    assert field.px_per_mm(500, 0) == pytest.approx(ppm(0), rel=1e-6)
    assert field.px_per_mm(500, 1000) == pytest.approx(ppm(1000), rel=1e-6)
    # Depth genuinely linear in y is exactly what the plane model fits -- residual ~0.
    assert field.residual_std_pct == pytest.approx(0.0, abs=1e-6)


def test_tags_without_a_known_size_are_ignored() -> None:
    pairs = _paired([
        _square_detection(0, 100, 100, 120),
        _square_detection(1, 900, 100, 120),
        _square_detection(2, 500, 900, 120),
    ])
    corner = printed_tag(450, 500, 500, 200)  # a corner tag, deliberately not in the size map
    field = build_scale_field(pairs + [corner], {d.tag_id: 30.0 for d in pairs})

    assert field.px_per_mm(500, 500) == pytest.approx(120 / 30, rel=1e-6)


def test_raises_with_fewer_than_three_usable_tags() -> None:
    detections = _paired([
        _square_detection(0, 100, 100, 120),
        _square_detection(1, 900, 100, 120),
    ])
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
    detections = _paired([
        _square_detection(tag_id, x, y, ppm(x, y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ])
    result = holdout_coverage_test(detections, _SIZES)

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
    detections = _paired([
        _square_detection(tag_id, x, y, ppm(x, y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ])
    result = holdout_coverage_test(detections, _SIZES)

    assert result.mean_abs_pct_error > 0.5


def test_holdout_is_reproducible_with_the_same_seed() -> None:
    positions = _grid_positions()
    detections = _paired([
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ])
    sizes = _SIZES

    first = holdout_coverage_test(detections, sizes, seed=7)
    second = holdout_coverage_test(detections, sizes, seed=7)
    assert first == second


def test_raises_with_fewer_than_six_usable_tags() -> None:
    detections = _paired([_square_detection(i, 100 * i, 100, 120) for i in range(5)])
    with pytest.raises(ValueError, match="at least 6"):
        holdout_coverage_test(detections, _SIZES)


def test_scale_variation_is_evaluated_over_the_tag_cloud_not_the_frame() -> None:
    # Tags only span x in [100, 900], y in [100, 900] -- a much smaller box than a real frame.
    # Depth (and so scale) varies with y only, over the *tag cloud's* extent.
    size_mm = 30.0
    ppm_at_centre = 4.0

    def ppm(y: float) -> float:
        depth = 1 + 0.2 * (y - 500) / 400
        return ppm_at_centre / depth

    positions = [(100, 100), (900, 100), (100, 900), (900, 900), (500, 500)]
    detections = _paired([
        _square_detection(tag_id, x, y, ppm(y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ])
    field = build_scale_field(detections, _SIZES)

    line = describe_scale_variation(field, [(x, y) for x, y in positions])
    expected_variation = 100.0 * (ppm(100) - ppm(900)) / ((ppm(100) + ppm(900)) / 2)
    assert f"{expected_variation:.0f}%" in line
    assert "top" in line  # y=100 (top, in image coords) is where scale is largest here


def test_scale_variation_line_names_the_worst_corner() -> None:
    detections = _paired([
        _square_detection(0, 0, 0, 100),
        _square_detection(1, 1000, 0, 100),
        _square_detection(2, 0, 1000, 100),
        _square_detection(3, 1000, 1000, 150),  # bottom-right: clearly the outlier
        _square_detection(4, 500, 500, 105),
    ])
    field = build_scale_field(detections, _SIZES)
    line = describe_scale_variation(field, [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)])
    assert "bottom-right" in line


def test_coplanarity_line_names_the_nearer_and_farther_corner() -> None:
    detections = _paired([
        _square_detection(0, 0, 0, 100),
        _square_detection(1, 1000, 0, 100),
        _square_detection(2, 0, 1000, 100),
        _square_detection(3, 1000, 1000, 150),  # bottom-right: nearer the camera (bigger px/mm)
        _square_detection(4, 500, 500, 105),
    ])
    field = build_scale_field(detections, _SIZES)
    line = describe_coplanarity(
        field, [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)]
    )
    assert "bottom-right" in line
    assert "top-left" in line
    assert "no tilt angle" in line.lower()


def test_coplanarity_line_reports_near_zero_span_when_field_is_flat() -> None:
    positions = [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)]
    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)])
    field = build_scale_field(detections, _SIZES)

    line = describe_coplanarity(field, positions)
    assert "0.0%" in line


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
    detections = _paired([
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ])
    sizes = _SIZES
    field = build_scale_field(detections, sizes)
    coverage = holdout_coverage_test(detections, sizes)

    report = build_install_report(field, positions, coverage)
    assert len(report) == 3
    assert "Scale varies" in report[0]
    assert "nearer the table" in report[1]
    assert "Coverage" in report[2]


def test_install_report_omits_coverage_line_when_not_given() -> None:
    positions = [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)]
    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)])
    field = build_scale_field(detections, _SIZES)

    report = build_install_report(field, positions)
    assert len(report) == 2


def test_regional_coverage_flags_an_empty_quadrant() -> None:
    # 3 tags each in top-right, bottom-left, bottom-right; none in top-left.
    positions = [
        (700, 100), (1000, 100), (700, 400),  # top-right
        (100, 700), (100, 1000), (400, 700),  # bottom-left
        (700, 700), (1000, 1000), (700, 1000),  # bottom-right
    ]
    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)])
    results = regional_coverage_test(
        detections, _SIZES, frame_width=1100, frame_height=1100
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
    detections = _paired([
        _square_detection(tag_id, x, y, ppm(x, y) * size_mm)
        for tag_id, (x, y) in enumerate(positions)
    ])
    results = regional_coverage_test(
        detections, _SIZES, frame_width=1100, frame_height=1100
    )

    by_quadrant = {r.quadrant: r for r in results}
    bottom_right = by_quadrant["bottom-right"]
    assert bottom_right.observed_count == 4
    assert bottom_right.mean_abs_pct_error > 5.0


def test_regional_coverage_reports_none_when_too_little_data_to_fit() -> None:
    positions = [(700, 100), (100, 700), (700, 700)]  # one tag each in 3 quadrants, none top-left
    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)])
    results = regional_coverage_test(
        detections, _SIZES, frame_width=1100, frame_height=1100
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
    detections = _paired([
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ])
    sizes = _SIZES
    field = build_scale_field(detections, sizes)
    regional = regional_coverage_test(detections, sizes, frame_width=1100, frame_height=1100)

    report = build_install_report(field, positions, None, regional)
    assert report[0].startswith("Scale varies")
    assert report[1].startswith("Scale reads")
    # Whatever regional lines exist (there may be none, if coverage is even) come after.
    assert len(report) == 2 + len(describe_regional_coverage(regional))


def test_calibration_artifact_round_trips_through_dict() -> None:
    from npec_rig.calibration import (
        CalibrationArtifact,
        calibration_artifact_from_dict,
        calibration_artifact_to_dict,
    )
    from npec_rig.tripwire import CornerBaseline

    field = build_scale_field(
        _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())]),
        _SIZES,
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
    assert data["version"] == 3
    restored = calibration_artifact_from_dict(data)

    assert restored == artifact


def test_calibration_artifact_without_a_baseline_round_trips() -> None:
    from npec_rig.calibration import CalibrationArtifact, calibration_artifact_from_dict, calibration_artifact_to_dict

    field = build_scale_field(
        _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())]),
        _SIZES,
    )
    artifact = CalibrationArtifact(created_at="2026-09-20T12:00:00+00:00", scale_field=field)

    restored = calibration_artifact_from_dict(calibration_artifact_to_dict(artifact))
    assert restored == artifact
    assert restored.corner_baseline is None


def test_calibration_artifact_with_frame_stem_round_trips() -> None:
    from npec_rig.calibration import (
        CalibrationArtifact,
        calibration_artifact_from_dict,
        calibration_artifact_to_dict,
    )

    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())])
    sizes = _SIZES
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00",
        scale_field=build_scale_field(detections, sizes),
        frame_stem="20260920T120000000000",
    )

    restored = calibration_artifact_from_dict(calibration_artifact_to_dict(artifact))
    assert restored == artifact
    assert restored.frame_stem == "20260920T120000000000"


def test_calibration_artifact_saved_with_an_uncertainty_field_still_loads() -> None:
    """Artifacts saved before issue #52 carry an "uncertainty_field" key; it is ignored."""
    from npec_rig.calibration import (
        CalibrationArtifact,
        calibration_artifact_from_dict,
        calibration_artifact_to_dict,
    )

    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(_grid_positions())])
    sizes = _SIZES
    artifact = CalibrationArtifact(
        created_at="2026-09-20T12:00:00+00:00", scale_field=build_scale_field(detections, sizes)
    )
    data = calibration_artifact_to_dict(artifact)
    data["uncertainty_field"] = {"positions": [[500.0, 500.0]], "residual_pct": [0.1]}

    assert calibration_artifact_from_dict(data) == artifact


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
    detections = _paired([
        _square_detection(tag_id, x, y, 120 + 0.01 * x)
        for tag_id, (x, y) in enumerate(positions)
    ])
    sizes = _SIZES

    report = build_calibration_report(detections, sizes, frame_width=1100, frame_height=1100)

    field = build_scale_field(detections, sizes)
    coverage = holdout_coverage_test(detections, sizes)
    regional = regional_coverage_test(detections, sizes, 1100, 1100)
    area = area_scale_samples(field, detections, sizes)
    expected = build_install_report(field, positions, coverage, regional, area)
    assert report == expected


def test_build_calibration_report_skips_coverage_line_with_too_few_tags_for_a_holdout() -> None:
    from npec_rig.calibration import build_calibration_report

    positions = [(100, 100), (900, 100), (500, 900), (100, 900), (900, 900)]
    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)])
    sizes = _SIZES

    report = build_calibration_report(detections, sizes, frame_width=1000, frame_height=1000)
    assert report[0].startswith("Scale varies")
    assert not any("Coverage sufficient" in line or "Coverage insufficient" in line for line in report)


def test_build_calibration_report_includes_area_scale_line() -> None:
    from npec_rig.calibration import build_calibration_report

    positions = _grid_positions()
    detections = _paired([_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)])
    sizes = _SIZES

    report = build_calibration_report(detections, sizes, frame_width=1100, frame_height=1100)
    assert any(line.startswith("Area-scale error") for line in report)


def test_scale_residual_samples_is_near_zero_for_consistent_squares() -> None:
    positions = _grid_positions()
    detections = _paired([_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)])
    sizes = _SIZES
    field = build_scale_field(detections, sizes)

    samples = scale_residual_samples(field, detections, sizes)
    assert len(samples) == len(detections)
    assert {s.tag_id for s in samples} == {d.tag_id for d in detections}
    for sample in samples:
        assert sample.residual_pct == pytest.approx(0.0, abs=1e-6)


def test_scale_residual_samples_matches_the_known_residual_for_an_off_plane_tag() -> None:
    size_mm = 30.0
    fit_positions = _grid_positions()
    fit_detections = _paired([
        _square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(fit_positions)
    ])
    field = build_scale_field(fit_detections, _SIZES)

    off_plane = _paired([_square_detection(9, 500, 500, 132)])  # tag spacing 4.4 px/mm, field 4.0
    samples = scale_residual_samples(field, off_plane, _SIZES)

    assert {s.tag_id for s in samples} == {d.tag_id for d in off_plane}
    for sample in samples:
        predicted = field.px_per_mm(sample.x, sample.y)
        assert sample.residual_pct == pytest.approx(100.0 * (132 / size_mm - predicted) / predicted, rel=1e-6)


def test_scale_residual_samples_skips_tags_the_field_cant_evaluate() -> None:
    field = ScaleField(_coeffs=(1.0, -0.001, 0.0), _mean_px_per_mm=4.0, residual_std_pct=0.0)
    in_domain = _paired([_square_detection(1, 100, 100, 120)])
    far_away = _paired([_square_detection(9, 2000, 100, 120)])  # relative_depth = -1, non-physical

    samples = scale_residual_samples(field, in_domain + far_away, _SIZES)
    assert {s.tag_id for s in samples} == {d.tag_id for d in in_domain}


def test_area_scale_samples_is_near_zero_for_consistent_squares() -> None:
    # Every detection is an exact square consistent with the plane it was fit from -- both the
    # length residual and the shape factor (square vs. its own mean side length) are exactly
    # zero, so area_error_pct and shape_factor_pct should be too.
    positions = _grid_positions()
    detections = _paired([_square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(positions)])
    sizes = _SIZES
    field = build_scale_field(detections, sizes)

    samples = area_scale_samples(field, detections, sizes)
    assert len(samples) == len(detections)
    for sample in samples:
        assert sample.area_error_pct == pytest.approx(0.0, abs=1e-6)
        assert sample.shape_factor_pct == pytest.approx(0.0, abs=1e-6)


def test_area_error_pct_at_zero_shape_distortion_is_the_squared_length_residual() -> None:
    # A flat field (ppm == 4.0 everywhere), then one held-out *square* tag (shape_factor == 0)
    # sitting 10% off that field -- isolates the other term of the area_error_pct identity
    # documented on AreaScaleSample: with kappa == 1, area_error_pct == 100 * ((1 + r) ** 2 - 1),
    # not just "2 * r" -- the approximation the docstring uses for the *typical* small-r case.
    size_mm = 30.0
    fit_positions = _grid_positions()
    fit_detections = _paired([
        _square_detection(tag_id, x, y, 120) for tag_id, (x, y) in enumerate(fit_positions)
    ])
    field = build_scale_field(fit_detections, _SIZES)

    off_plane = _paired([_square_detection(9, 500, 500, 132)])  # tag spacing 4.4 px/mm, field 4.0
    samples = area_scale_samples(field, off_plane, _SIZES)

    assert len(samples) == 2
    for sample in samples:
        r = 132 / (size_mm * field.px_per_mm(sample.x, sample.y)) - 1.0
        assert sample.shape_factor_pct == pytest.approx(0.0, abs=1e-6)
        assert sample.area_error_pct == pytest.approx(100.0 * ((1.0 + r) ** 2 - 1.0), rel=1e-6)


def test_shape_factor_pct_isolates_distortion_when_length_residual_is_zero() -> None:
    # A non-square (rectangle) tag whose *mean side length* exactly matches what the field
    # predicts (zero length residual) but whose true shoelace area doesn't match side**2 --
    # the case AreaScaleSample exists to catch, and where area_error_pct and shape_factor_pct
    # must come out identical (the identity's other term is exactly zero).
    size_mm = 30.0
    width, height = 180.0, 88.0
    mean_side = (width + height) / 2  # what tag_side_px reports for a rectangle
    ppm = mean_side / size_mm

    # A flat field with exactly this scale everywhere, built from ordinary square tags.
    fit_positions = _grid_positions()
    fit_detections = _paired([
        _square_detection(tag_id, x, y, ppm * size_mm)
        for tag_id, (x, y) in enumerate(fit_positions)
    ])
    field = build_scale_field(fit_detections, _SIZES)

    # Two such rectangles, a printed pair spaced at exactly that scale, corners in the detector's
    # order (the page's x direction from corner 1 to corner 0, as `printed_tag`).
    a, b = _PAIRS[0]
    rectangles = [
        TagDetection(
            tag_id=tag_id,
            corners=(
                (cx + width / 2, 500 - height / 2),
                (cx - width / 2, 500 - height / 2),
                (cx - width / 2, 500 + height / 2),
                (cx + width / 2, 500 + height / 2),
            ),
            centre=(cx, 500.0),
        )
        for tag_id, cx in ((a, 500 - 37.5 / 2 * ppm), (b, 500 + 37.5 / 2 * ppm))
    ]
    samples = area_scale_samples(field, rectangles, _SIZES)

    assert len(samples) == 2
    expected_kappa = (width * height) / (mean_side**2)
    expected_pct = 100.0 * (expected_kappa - 1.0)
    for sample in samples:
        assert sample.shape_factor_pct == pytest.approx(expected_pct, rel=1e-6)
        assert sample.area_error_pct == pytest.approx(expected_pct, rel=1e-6)


def test_area_scale_samples_skips_tags_the_field_cant_evaluate() -> None:
    # A tilted field constructed directly (not fit) so the non-physical region is known exactly:
    # relative_depth = 1 - 0.001 * x, which goes to zero at x=1000 and negative beyond it.
    field = ScaleField(_coeffs=(1.0, -0.001, 0.0), _mean_px_per_mm=4.0, residual_std_pct=0.0)

    in_domain = _paired([_square_detection(1, 100, 100, 120)])
    far_away = _paired([_square_detection(9, 2000, 100, 120)])  # relative_depth = -1, non-physical

    samples = area_scale_samples(field, in_domain + far_away, _SIZES)
    assert {s.tag_id for s in samples} == {d.tag_id for d in in_domain}


def test_describe_area_scale_shape_reports_mean_and_worst_tag() -> None:
    # shape_factor_pct is <= 0 always (see AreaScaleSample) -- both samples respect that.
    samples = [
        AreaScaleSample(x=100.0, y=100.0, tag_id=1, area_error_pct=1.0, shape_factor_pct=-0.02),
        AreaScaleSample(x=900.0, y=900.0, tag_id=2, area_error_pct=-9.0, shape_factor_pct=-0.35),
    ]
    line = describe_area_scale_shape(samples)
    assert line.startswith("Area-scale error")
    assert "2 tags" in line
    assert "tag 2" in line
    assert "-0.35%" in line
    assert "(900, 900)" in line


def test_describe_area_scale_shape_raises_with_zero_samples() -> None:
    with pytest.raises(ValueError, match="at least one"):
        describe_area_scale_shape([])


def test_install_report_includes_area_scale_line_when_given() -> None:
    positions = [(0, 0), (1000, 0), (0, 1000), (1000, 1000), (500, 500)]
    detections = _paired([_square_detection(i, x, y, 120) for i, (x, y) in enumerate(positions)])
    sizes = _SIZES
    field = build_scale_field(detections, sizes)
    area = area_scale_samples(field, detections, sizes)

    report = build_install_report(field, positions, None, None, area)
    assert len(report) == 3
    assert report[2].startswith("Area-scale error")


def _corner_baseline(points_by_id: dict[int, tuple[float, float]], side_px: float = 20.0) -> CornerBaseline:
    """A `CornerBaseline` whose tags' centres land exactly at `points_by_id`'s pixel positions --
    `square_detection`'s corners average back to exactly (cx, cy), so this gives `TableFrame`
    tests an exact, known geometry to check against, not an approximation.
    """
    return CornerBaseline(
        corners_by_id={
            tag_id: _square_detection(tag_id, cx, cy, side_px).corners
            for tag_id, (cx, cy) in points_by_id.items()
        }
    )


def test_build_table_frame_round_trips_pixel_to_fraction() -> None:
    baseline = _corner_baseline({450: (0, 0), 451: (1000, 0), 452: (1000, 800), 455: (0, 800)})
    frame = build_table_frame(baseline)
    x, y = frame.to_pixel(*frame.to_fraction(300.0, 450.0))
    assert x == pytest.approx(300.0, abs=1e-6)
    assert y == pytest.approx(450.0, abs=1e-6)


def test_build_table_frame_centre_maps_to_half_half() -> None:
    baseline = _corner_baseline({450: (0, 0), 451: (1000, 0), 452: (1000, 800), 455: (0, 800)})
    frame = build_table_frame(baseline)
    u, v = frame.to_fraction(500.0, 400.0)
    assert u == pytest.approx(0.5, abs=1e-6)
    assert v == pytest.approx(0.5, abs=1e-6)


def test_build_table_frame_pins_corners_regardless_of_tag_id_order() -> None:
    # Tag IDs deliberately not laid out in TL/TR/BR/BL id order -- corner-role assignment must be
    # purely geometric (sum/difference trick on centroid coordinates), never derived from ID order
    # or ID adjacency (the real rig's own corner tags, 450/451/452/455, aren't contiguous either).
    baseline = _corner_baseline({452: (0, 0), 455: (1000, 0), 450: (1000, 800), 451: (0, 800)})
    frame = build_table_frame(baseline)
    assert frame.to_fraction(0.0, 0.0) == pytest.approx((0.0, 0.0), abs=1e-6)
    assert frame.to_fraction(1000.0, 0.0) == pytest.approx((1.0, 0.0), abs=1e-6)
    assert frame.to_fraction(1000.0, 800.0) == pytest.approx((1.0, 1.0), abs=1e-6)
    assert frame.to_fraction(0.0, 800.0) == pytest.approx((0.0, 1.0), abs=1e-6)


def test_build_table_frame_raises_with_wrong_corner_count() -> None:
    baseline = _corner_baseline({450: (0, 0), 451: (1000, 0), 452: (1000, 800)})
    with pytest.raises(ValueError, match="exactly 4"):
        build_table_frame(baseline)


def test_build_table_frame_raises_on_near_collinear_triple() -> None:
    # Today's real condition is 4 well-spread corner tags -- this guard is still real: three of
    # these four centres sit almost exactly on the same line (y ~= 0).
    baseline = _corner_baseline({450: (0, 0), 451: (500, 0.001), 452: (1000, 0), 455: (500, 800)})
    with pytest.raises(ValueError, match="collinear"):
        build_table_frame(baseline)


def test_build_table_frame_raises_on_self_intersecting_winding() -> None:
    # One centre (455) sits inside the triangle formed by the other three, rather than at a
    # fourth corner -- the sum/difference role assignment still picks TL/TR/BR/BL from these 4
    # points, but tracing them in that order self-intersects rather than forming a simple quad.
    baseline = _corner_baseline({450: (0, 0), 451: (1000, 0), 452: (1000, 1000), 455: (400, 200)})
    with pytest.raises(ValueError, match="bowtie"):
        build_table_frame(baseline)


def test_build_table_frame_fixes_arbitrary_svd_null_space_sign() -> None:
    # SVD's null-space vector (the DLT's raw solution, before build_table_frame's own sign fix)
    # comes back up to an arbitrary +/-1 sign -- both signs solve the same linear system, but only
    # one gives every real query inside the quad a physically valid (w > 0) result; the other
    # makes to_fraction/to_pixel raise everywhere inside the table, which would read as "never
    # measured anywhere" with no exception surfaced (see build_table_frame's own comment on this).
    # This exact quad was found, searching real (non-degenerate) random quads directly against
    # `_dlt_homography` with the sign fix *not* applied, to come back with the "wrong" raw sign --
    # a real regression case, not just an invariant restated as a test.
    baseline = _corner_baseline(
        {
            450: (344.4228640964949, 69.51537853084733),
            451: (168.14494622242825, 272.9144368186801),
            452: (109.48862729435938, 624.8020841524763),
            455: (159.6255246938475, 527.3803990480128),
        }
    )
    frame = build_table_frame(baseline)
    cx = (344.4228640964949 + 168.14494622242825 + 109.48862729435938 + 159.6255246938475) / 4
    cy = (69.51537853084733 + 272.9144368186801 + 624.8020841524763 + 527.3803990480128) / 4
    u, v = frame.to_fraction(cx, cy)
    assert 0.0 < u < 1.0
    assert 0.0 < v < 1.0


def test_build_table_frame_only_input_is_corner_baseline() -> None:
    # Cheap "never touches mm" check: build_table_frame's only parameter type is CornerBaseline --
    # no ScaleField parameter exists, so mm can't leak into this transform even by accident.
    (only_param,) = inspect.signature(build_table_frame).parameters.values()
    assert only_param.annotation == "CornerBaseline"
