"""The validation rules, called directly with tag detections: no web server, no camera (#182)."""

import pytest

from npec_rig import validation
from npec_rig.calibration import CalibrationArtifact, ScaleField
from npec_rig.calibration_store import save_calibration
from npec_rig.certainty_map import (
    build_slot_layout,
    calibration_centres,
    group_sheets,
    slot_layout_to_dict,
)
from tests.helpers import stored_validation, tray_layout_detections

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


def test_a_replayed_photo_on_the_test_bench_still_counts() -> None:
    # The replay flag warns a person; it does not hold a test bench round back (#279).
    round_ = _judge(tray_layout_detections(shift=(200, -150)), _record(flags=["replayed from a.jpg"]))
    assert round_["counted"] is True
    assert round_["reason"] is None


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


# --- Which validation is current (#183): the photo record and the status line use one rule ---

STEM = "20261009T073108292325"


@pytest.fixture(autouse=True)
def isolated_calibration_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _calibrate(lens_position: float = 6.05) -> None:
    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-09T07:31:08+00:00",
            scale_field=FIELD,
            frame_stem=STEM,
            lens_position=lens_position,
        )
    )


def test_no_calibration_is_not_covered() -> None:
    assert validation.photo_check(LOCKED) == {"session": None, "flagged": True, "reason": "no calibration"}


def test_unlocked_focus_is_left_to_the_lens_check() -> None:
    _calibrate()
    assert validation.photo_check({"locked": False, "lens_position": None}) == {
        "session": None, "flagged": False, "reason": None
    }


def test_a_lock_away_from_the_calibration_is_not_covered() -> None:
    _calibrate()
    stored_validation("20261009T080000000000", STEM)
    check = validation.photo_check({"locked": True, "lens_position": 6.50})
    assert check["session"] is None
    assert check["reason"] == "focus is locked at 6.50, the calibration was taken at 6.05"


def test_only_a_complete_validation_of_this_calibration_applies() -> None:
    _calibrate()
    stored_validation("20261009T080000000000", STEM, rounds=2)  # still running
    stored_validation("20261008T080000000000", "20261008T073108292325")  # another calibration
    check = validation.photo_check(LOCKED)
    assert check == {"session": None, "flagged": True, "reason": "no finished validation of this calibration"}


def test_the_newest_complete_validation_applies() -> None:
    _calibrate()
    stored_validation("20261009T080000000000", STEM)
    stored_validation("20261009T100000000000", STEM)
    assert validation.photo_check(LOCKED) == {"session": "20261009T100000000000", "flagged": False, "reason": None}


def test_a_newer_validation_that_is_not_complete_does_not_replace_the_current_one() -> None:
    # Aaron, 2026-10-16: a validation started by mistake must not take away the good one.
    _calibrate()
    stored_validation("20261009T080000000000", STEM)
    stored_validation("20261009T100000000000", STEM, rounds=1)
    stored_validation("20261009T110000000000", STEM, rounds=2, ended=True)
    assert validation.photo_check(LOCKED)["session"] == "20261009T080000000000"
    status = validation.status(LOCKED)
    assert (status["state"], status["session_id"]) == ("validated", "20261009T080000000000")
    assert status["text"] == (
        "Validated 2026-10-09; a newer validation ended after 2 of 3 rounds"
    )


def test_a_current_validation_that_is_not_consistent_flags_photos_but_names_itself() -> None:
    _calibrate()
    stored_validation("20261009T080000000000", STEM)
    stored_validation("20261009T100000000000", STEM, inconsistent=True)
    assert validation.photo_check(LOCKED) == {
        "session": "20261009T100000000000",
        "flagged": True,
        "reason": "the validation is not consistent: North 1",
    }
    status = validation.status(LOCKED)
    assert (status["state"], status["text"]) == ("not_consistent", "Not consistent: North 1")


def test_the_status_line_names_a_newer_validation_in_progress_and_its_problem() -> None:
    _calibrate()
    stored_validation("20261009T080000000000", STEM)
    stored_validation("20261009T100000000000", STEM, rounds=2, inconsistent=True)
    assert validation.status(LOCKED)["text"] == (
        "Validated 2026-10-09; a newer validation is in progress, 2 of 3 rounds, "
        "not consistent: North 1"
    )


def test_with_no_complete_validation_the_status_line_shows_the_newest_ones_progress() -> None:
    _calibrate()
    stored_validation("20261009T100000000000", STEM, rounds=2, inconsistent=True)
    assert validation.status(LOCKED)["text"] == "Not consistent: North 1"
    stored_validation("20261009T110000000000", STEM, rounds=1)
    status = validation.status(LOCKED)
    assert (status["state"], status["text"]) == ("not_validated", "Not validated: 1 of 3 rounds counted so far")


def test_a_damaged_current_validation_flags_the_photo_instead_of_failing_it() -> None:
    from npec_rig import validation_store

    _calibrate()
    session = stored_validation("20261009T080000000000", STEM)
    del session["slots"]
    validation_store.save_session(session)
    assert validation.photo_check(LOCKED) == {
        "session": "20261009T080000000000",
        "flagged": True,
        "reason": "the validation record could not be read",
    }


def _edges_short(detections, factor: float = 0.98):
    """`detections` with every tag edge `factor` as long, centres unmoved: the real photos' fault."""
    from npec_rig.tags import TagDetection

    return [
        TagDetection(d.tag_id, tuple((d.centre[0] + factor * (x - d.centre[0]), d.centre[1] + factor * (y - d.centre[1])) for x, y in d.corners), d.centre)
        for d in detections
    ]


def test_a_twin_gets_its_original_validation_scored_again_by_tag_spacing(isolated_settings_db) -> None:
    # Part B, test point 3 (#286). The original calibration was fitted to tag edges, 2% short: 3.92
    # px/mm where the tags are spaced at exactly 4.00. Its validation, scored the old way (edges
    # against 3.92), read 0.0% in every slot. Scored again for the twin (4.00), every slot reads
    # 0.0% by tag spacing too, and the table passes. The original validation file is unchanged.
    from npec_rig import images, validation_store

    original_stem, twin_stem = "20261016T090000000000", "20261026T150000000000"
    save_calibration(
        CalibrationArtifact(created_at="2026-10-16T09:00:00+00:00", scale_field=ScaleField((1.0, 0.0, 0.0), 3.92, 0.0),
                            lens_position=6.05, calibration_tag_size_mm=30.0, frame_stem=original_stem),
        stem=original_stem, promote=False,
    )
    save_calibration(
        CalibrationArtifact(created_at="2026-10-26T15:00:00+00:00", scale_field=FIELD, lens_position=6.05,
                            calibration_tag_size_mm=30.0, frame_stem=original_stem, rebuilt_from=original_stem),
        stem=twin_stem, promote=False,
    )
    session = validation_store.new_session(original_stem, _session()["slots"], _session()["calibration_centres"])
    for i, shift in enumerate(((200, -150), (-250, 100), (150, 200))):
        ref = f"2026-10-16/1{i}0000_000000"
        images.store_tag_detections(ref, _edges_short(tray_layout_detections(shift=shift)))
        session["rounds"].append({
            "capture": ref, "captured_at": f"2026-10-16T1{i}:00:00+00:00", "moved_pct": 90.0, "counted": True,
            "overridden": False, "reason": None, "overridable": False, "centres": [],
            "slot_errors": {slot["name"]: [0.0] * 30 for slot in session["slots"]},
        })
    validation_store.refresh_results(session)
    validation_store.save_session(session)
    original_file = validation_store.validations_root() / f"{session['id']}.json"
    before = original_file.read_bytes()

    rescored = validation.rescore(twin_stem)

    assert rescored["calibration_stem"] == twin_stem
    assert rescored["rescored_from"] == session["id"]
    assert len(rescored["rounds"]) == 3
    for round_ in rescored["rounds"]:
        assert round_["counted"]
        for errors in round_["slot_errors"].values():
            assert errors == pytest.approx([0.0] * 30, abs=1e-6)
    assert validation_store.offset_problems(rescored) == []
    assert original_file.read_bytes() == before
    # By tag spacing against the original's 3.92 px/mm the bias shows: (4.00 / 3.92)^2 - 1 = +4.12%.
    from npec_rig.certainty_map import round_errors_by_slot, slot_layout_from_dict

    against_original = round_errors_by_slot(
        _edges_short(tray_layout_detections(shift=(200, -150))), slot_layout_from_dict(session["slots"]),
        ScaleField((1.0, 0.0, 0.0), 3.92, 0.0), 30.0,
    )
    for errors in against_original.values():
        assert errors == pytest.approx([4.12] * 30, abs=0.01)
