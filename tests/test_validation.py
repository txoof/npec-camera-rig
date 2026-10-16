"""The validation rules, called directly with tag detections: no web server, no camera (#182)."""

import pytest

from npec_rig import validation
from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.certainty_map import (
    build_slot_layout,
    calibration_centres,
    group_sheets,
    slot_layout_to_dict,
)
from tests.helpers import tray_layout_detections

pytestmark = pytest.mark.unit

# Uniform 4 px/mm, so a 30 mm tag is exactly 120 px across and reads 0% error.
FIELD = ScaleField((1.0, 0.0, 0.0), 4.0, 0.0)
ARTIFACT = CalibrationArtifact(
    created_at="2026-10-16T00:00:00+00:00",
    scale_field=FIELD,
    lens_position=6.05,
    calibration_tag_size_mm=30.0,
)
LOCKED = {"locked": True, "lens_position": 6.05}


def _session() -> dict:
    """A session whose tray slots and reference centres come from the unshifted layout."""
    calibration = tray_layout_detections()
    layout = build_slot_layout(group_sheets(calibration, FIELD, 30.0))
    return {
        "slots": slot_layout_to_dict(layout),
        "calibration_centres": [list(c) for c in calibration_centres(calibration)],
        "rounds": [],
    }


def _record(focus: dict = LOCKED, flags: list[str] | None = None) -> dict:
    return {"timestamp": "2026-10-16T10:00:00+00:00", "focus": focus, "flags": flags or []}


def _judge(detections, record=None) -> dict:
    return validation.judge_round(_session(), ARTIFACT, detections, record or _record(), "2026-10-16/100000_000000")


def test_a_moved_round_at_the_calibration_focus_counts() -> None:
    round_ = _judge(tray_layout_detections(shift=(200, -150)))
    assert round_["counted"] is True
    assert round_["reason"] is None
    assert round_["moved_pct"] == 100.0
    assert set(round_["slot_errors"]) == {slot["name"] for slot in _session()["slots"]}


def test_a_round_where_nothing_moved_is_held_back_and_can_be_counted_anyway() -> None:
    round_ = _judge(tray_layout_detections())
    assert round_["counted"] is False
    assert round_["overridable"] is True
    assert round_["reason"].startswith("only 0% of tags moved")


def test_a_round_at_another_focus_is_held_back_and_can_be_counted_anyway() -> None:
    round_ = _judge(tray_layout_detections(shift=(200, -150)), _record({"locked": True, "lens_position": 6.50}))
    assert (round_["counted"], round_["overridable"]) == (False, True)
    assert round_["reason"] == "focus is locked at 6.50, the calibration was taken at 6.05"


def test_a_flagged_photo_is_held_back_but_focus_not_locked_is_reported_once() -> None:
    record = _record({"locked": False, "lens_position": None}, flags=["focus not locked", "camera started 5 min ago"])
    round_ = _judge(tray_layout_detections(shift=(200, -150)), record)
    assert round_["reason"] == "focus is not locked; camera started 5 min ago"
    assert round_["overridable"] is True


def test_a_round_missing_a_sheet_cannot_be_counted_and_still_names_the_focus() -> None:
    record = _record({"locked": True, "lens_position": 6.50})
    round_ = _judge(tray_layout_detections(shift=(200, -150))[30:], record)
    assert round_["counted"] is False
    assert round_["overridable"] is False
    assert round_["slot_errors"] is None
    assert round_["reason"].startswith("focus is locked at 6.50, the calibration was taken at 6.05; ")


def test_focus_problem() -> None:
    assert validation.focus_problem(LOCKED, ARTIFACT) is None
    assert validation.focus_problem({"locked": True, "lens_position": 6.054}, ARTIFACT) is None
    assert validation.focus_problem({"locked": False, "lens_position": None}, ARTIFACT) == "focus is not locked"
    no_lens = CalibrationArtifact(created_at="2026-10-16T00:00:00+00:00", scale_field=FIELD)
    assert validation.focus_problem({"locked": True, "lens_position": 9.0}, no_lens) is None
