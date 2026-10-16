"""The calibration run's rules without HTTP: the readiness gate's answer and the comparison with
the calibration a run replaces. The run itself is tested over HTTP in
tests/web/test_calibration_routes.py."""

import pytest

from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.calibration_run import CORNER_TAGS_REQUIRED, gate_refusal, previous_comparison
from npec_rig.tripwire import CornerBaseline

pytestmark = pytest.mark.unit


def _ready(focus_locked: bool, corner_tags_detected: int) -> dict:
    return {
        "focus_locked": focus_locked,
        "corner_tags_detected": corner_tags_detected,
        "corner_tags_required": CORNER_TAGS_REQUIRED,
        "ready": focus_locked and corner_tags_detected >= CORNER_TAGS_REQUIRED,
    }


def test_gate_lets_a_ready_run_through():
    assert gate_refusal(_ready(True, 4)) is None


def test_gate_names_focus_first_when_both_fail():
    refusal = gate_refusal(_ready(False, 0))
    assert refusal["gate_failed"] is True
    assert refusal["error"].startswith("Focus is not confirmed")
    # The readiness numbers go back with the refusal, for the wizard's own line.
    assert refusal["corner_tags_detected"] == 0


def test_gate_counts_the_corner_tags_it_saw():
    refusal = gate_refusal(_ready(True, 3))
    assert refusal["error"] == (
        "3 of 4 corner tags detected. A minimum of 4 is required for a successful calibration."
    )


def _comparison(previous: CalibrationArtifact | None) -> dict | None:
    return previous_comparison(
        previous,
        residual_std_pct=0.8,
        corner_tag_count=4,
        calibration_tag_size_mm=30.0,
        lens_position=6.05,
        px_per_mm_at_centre=5.0,
        frame_width=1000,
        frame_height=800,
    )


def test_no_comparison_for_the_first_calibration():
    assert _comparison(None) is None


def test_comparison_gives_previous_current_and_change():
    previous = CalibrationArtifact(
        created_at="2026-10-14T08:00:00+00:00",
        scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
        corner_baseline=CornerBaseline(corners_by_id={1: None, 2: None}),
        lens_position=6.0,
        calibration_tag_size_mm=30.0,
    )
    comparison = _comparison(previous)
    assert comparison["previous_created_at"] == "2026-10-14T08:00:00+00:00"
    assert comparison["corner_tags_detected"] == {"previous": 2, "current": 4, "delta": 2}
    assert comparison["px_per_mm_at_centre"] == {"previous": 4.0, "current": 5.0, "delta": 1.0}
    assert comparison["residual_std_pct"]["delta"] == pytest.approx(-0.2)
    assert comparison["lens_position"]["delta"] == pytest.approx(0.05)
    assert comparison["calibration_tag_size_mm"]["delta"] == 0.0


def test_comparison_without_a_previous_scale_at_the_centre():
    # A previous field that is not physically valid at the centre and no corner baseline: those
    # two have no previous value, so no change either.
    previous = CalibrationArtifact(
        created_at="2026-10-14T08:00:00+00:00",
        scale_field=ScaleField(_coeffs=(0.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
    )
    comparison = _comparison(previous)
    assert comparison["px_per_mm_at_centre"] == {"previous": None, "current": 5.0, "delta": None}
    assert comparison["corner_tags_detected"]["previous"] == 0
    assert comparison["lens_position"] == {"previous": None, "current": 6.05, "delta": None}
