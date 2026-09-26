import pytest

from npec_rig.tripwire import (
    CornerBaseline,
    build_corner_baseline,
    check_tripwire,
    corner_level_readings,
)

from .helpers import rotate_detection, square_detection

pytestmark = pytest.mark.unit

CORNER_LAYOUT = [(0, 0), (1000, 0), (0, 1000), (1000, 1000)]


def _corner_detections(tag_ids: list[int] = (450, 451, 452, 453), side_px: float = 100) -> list:
    return [
        square_detection(tag_id, cx, cy, side_px)
        for tag_id, (cx, cy) in zip(tag_ids, CORNER_LAYOUT)
    ]


def test_build_corner_baseline_uses_only_corner_range_tags() -> None:
    detections = _corner_detections() + [square_detection(5, 500, 500, 120)]  # a tray tag
    baseline = build_corner_baseline(detections)
    assert sorted(baseline.corners_by_id) == [450, 451, 452, 453]


def test_build_corner_baseline_accepts_fewer_than_four() -> None:
    # All 4 mounted corner tags are detected in every recent real run (verified against saved
    # calibration artifacts) -- but a corner tag could still be knocked loose or obstructed
    # later, so this guard (a baseline with fewer than 4 entries) stays real, not dead code.
    detections = _corner_detections(tag_ids=[450, 451, 452])
    baseline = build_corner_baseline(detections)
    assert sorted(baseline.corners_by_id) == [450, 451, 452]


def test_build_corner_baseline_raises_with_no_corner_tags() -> None:
    with pytest.raises(ValueError, match="no corner tags"):
        build_corner_baseline([square_detection(5, 500, 500, 120)])


def test_ok_when_nothing_has_moved() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    result = check_tripwire(baseline, detections)
    assert result.verdict == "OK"
    assert result.roll_deg == pytest.approx(0.0, abs=1e-6)


def test_missing_baseline_tag_fails_loud() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    current = _corner_detections(tag_ids=[450, 451, 452])  # 453 missing this capture
    result = check_tripwire(baseline, current)
    assert result.verdict == "FAIL"
    assert "453" in result.messages[0]
    assert result.roll_deg is None


def test_missing_tag_the_baseline_never_had_does_not_fail() -> None:
    # Baseline only has 3 corners (e.g. one obstructed at calibration time) -- the tripwire must
    # not demand a 4th tag it was never given.
    baseline = build_corner_baseline(_corner_detections(tag_ids=[450, 451, 452]))
    current = _corner_detections(tag_ids=[450, 451, 452])  # same 3, unmoved; no 453 either time
    result = check_tripwire(baseline, current)
    assert result.verdict == "OK"


def test_a_small_deliberate_roll_is_reported_accurately_and_drifts() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    rotated = [rotate_detection(d, (500, 500), 5.0) for d in detections]

    result = check_tripwire(baseline, rotated)
    assert result.roll_deg == pytest.approx(5.0, abs=0.05)
    assert result.verdict == "DRIFT"
    assert "5.0" in result.messages[0]
    assert "clockwise" in result.messages[0]


def test_counterclockwise_roll_reports_the_opposite_direction() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    rotated = [rotate_detection(d, (500, 500), -5.0) for d in detections]

    result = check_tripwire(baseline, rotated)
    assert result.roll_deg == pytest.approx(-5.0, abs=0.05)
    assert "counterclockwise" in result.messages[0]


def test_a_hard_knock_fails() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    knocked = [rotate_detection(d, (500, 500), 25.0) for d in detections]

    result = check_tripwire(baseline, knocked)
    assert result.verdict == "FAIL"


def test_scale_change_reports_closer_or_farther() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    # Corner tag 453 is now 5% bigger (closer) than at calibration time; others unchanged.
    closer = _corner_detections()
    closer[3] = square_detection(453, 1000, 1000, 105)

    result = check_tripwire(baseline, closer)
    assert result.verdict == "DRIFT"
    assert result.scale_delta_pct[453] == pytest.approx(5.0, abs=0.1)
    assert any("453" in m and "closer" in m for m in result.messages)


def test_scale_change_the_other_direction_reports_farther() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    farther = _corner_detections()
    farther[3] = square_detection(453, 1000, 1000, 90)

    result = check_tripwire(baseline, farther)
    assert any("farther" in m for m in result.messages)


def test_large_scale_change_fails() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    much_closer = _corner_detections()
    much_closer[3] = square_detection(453, 1000, 1000, 130)  # 30% bigger

    result = check_tripwire(baseline, much_closer)
    assert result.verdict == "FAIL"


def test_a_single_matched_tag_refuses_rather_than_guesses_a_roll() -> None:
    # Only 1 corner tag survived (badly obscured, or the other 3 didn't detect this capture) --
    # not enough cross-tag geometry to say anything about roll/drift confidently.
    baseline = build_corner_baseline(_corner_detections(tag_ids=[450]))
    current = _corner_detections(tag_ids=[450])  # unmoved -- still refuses, not "OK"

    result = check_tripwire(baseline, current)
    assert result.verdict == "FAIL"
    assert result.roll_deg is None
    assert result.scale_delta_pct is None
    assert "not enough" in result.messages[0]


def test_thresholds_are_overridable() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    rotated = [rotate_detection(d, (500, 500), 2.0) for d in detections]

    # Default drift threshold (1 deg) would flag this; a looser one shouldn't.
    result = check_tripwire(baseline, rotated, roll_drift_deg=5.0, roll_fail_deg=20.0)
    assert result.verdict == "OK"


def test_level_readings_all_ok_when_all_corners_are_the_same_size() -> None:
    readings = corner_level_readings(_corner_detections())
    assert len(readings) == 4
    assert all(r.status == "ok" for r in readings)
    assert all(r.deviation_pct == pytest.approx(0.0, abs=1e-6) for r in readings)


def test_level_readings_flag_a_closer_corner_regardless_of_where_it_sits() -> None:
    # Deliberately asymmetric layout (not centred, not evenly spaced) -- the physics this checks
    # (apparent size depends on distance from the camera, not position in a fronto-parallel
    # plane) doesn't care where each tag is mounted, only how far it is from the others' size.
    detections = [
        square_detection(450, 0, 0, 100),
        square_detection(451, 1200, 50, 100),
        square_detection(452, 30, 1500, 100),
        square_detection(453, 1400, 1600, 106),  # ~6% bigger -- closer to the camera
    ]
    readings = corner_level_readings(detections)
    by_id = {r.tag_id: r for r in readings}
    assert by_id[453].status == "drift"
    assert by_id[453].deviation_pct > 0
    assert by_id[450].status == "ok"


def test_level_readings_fail_band_at_a_large_deviation() -> None:
    detections = _corner_detections()
    detections[3] = square_detection(453, 1000, 1000, 130)  # 30% bigger than the other three
    readings = corner_level_readings(detections)
    by_id = {r.tag_id: r for r in readings}
    assert by_id[453].status == "fail"


def test_level_readings_mean_excludes_self_at_the_two_tag_minimum() -> None:
    # Found by code review 2026-09-26: with the minimum supported 2 tags, a mean that includes
    # each tag itself dilutes a real 16% size difference to ~7.4% each -- under the 8% fail
    # threshold. Excluding self recovers the true magnitude (per the docstring's own claim).
    detections = [
        square_detection(450, 0, 0, 100),
        square_detection(451, 1000, 1000, 116),  # 16% bigger than the other
    ]
    readings = corner_level_readings(detections)
    by_id = {r.tag_id: r for r in readings}
    assert by_id[451].deviation_pct == pytest.approx(16.0)
    assert by_id[451].status == "fail"
    assert by_id[450].deviation_pct == pytest.approx(100 / 116 * 100 - 100)
    assert by_id[450].status == "fail"


def test_level_readings_empty_with_fewer_than_two_corner_tags() -> None:
    assert corner_level_readings(_corner_detections(tag_ids=[450])) == []
    assert corner_level_readings([]) == []


def test_level_readings_ignore_non_corner_tags() -> None:
    detections = _corner_detections() + [square_detection(5, 500, 500, 500)]  # a tray tag
    readings = corner_level_readings(detections)
    assert {r.tag_id for r in readings} == {450, 451, 452, 453}


def test_level_readings_thresholds_are_overridable() -> None:
    detections = _corner_detections()
    detections[3] = square_detection(453, 1000, 1000, 104)  # 4% bigger
    readings = corner_level_readings(detections, drift_pct=5.0, fail_pct=10.0)
    assert all(r.status == "ok" for r in readings)
