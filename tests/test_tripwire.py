import pytest

from npec_rig.tripwire import (
    CornerBaseline,
    build_corner_baseline,
    check_tripwire,
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
    # One of the four mounted corner tags is currently partially obscured (TODO.md) -- a real
    # baseline may legitimately have 3 entries, not 4.
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
    # Baseline only has 3 corners (one obscured at calibration time) -- the tripwire must not
    # demand a 4th tag it was never given.
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


def test_thresholds_are_overridable() -> None:
    detections = _corner_detections()
    baseline = build_corner_baseline(detections)
    rotated = [rotate_detection(d, (500, 500), 2.0) for d in detections]

    # Default drift threshold (1 deg) would flag this; a looser one shouldn't.
    result = check_tripwire(baseline, rotated, roll_drift_deg=5.0, roll_fail_deg=20.0)
    assert result.verdict == "OK"
