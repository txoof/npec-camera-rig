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


def _stored_calibration(stem: str, frame_stem: str, px_per_mm: float) -> None:
    """A saved calibration fitted (as before #286) to tag edges at `px_per_mm`, its photo's tags
    stored as a calibration run stores them: four tag sheets spaced at exactly 5.00 px/mm."""
    from npec_rig import calibration_store, images

    from tests.helpers import printed_sheet

    ref = f"{frame_stem[0:4]}-{frame_stem[4:6]}-{frame_stem[6:8]}/{frame_stem[9:15]}_{frame_stem[15:21]}"
    tags = [
        d
        for page, (x0, y0) in ((2, (500, 2000)), (3, (6500, 2000)), (4, (500, 6000)), (5, (6500, 6000)))
        for d in printed_sheet(page, x0, y0, 5.0, edge_scale=0.98)
    ]
    images.store_tag_detections(ref, tags)
    artifact = CalibrationArtifact(
        created_at="2026-10-22T07:25:23+00:00",
        scale_field=ScaleField((1.0, 0.0, 0.0), px_per_mm, 0.5),
        calibration_tag_size_mm=30.0,
        frame_stem=frame_stem,
    )
    calibration_store.save_calibration(artifact, stem=stem, promote=False)


def test_a_rebuild_makes_a_twin_from_tag_spacing_and_leaves_the_original(isolated_settings_db):
    # Part B, test point 1 (#286): an original fitted to tag edges at 4.90 px/mm, its photo's tags
    # spaced at exactly 5.00. The twin reads 5.00; the original file stays byte for byte the same.
    from npec_rig import calibration_store
    from npec_rig.calibration_run import rebuild

    _stored_calibration("20261022T072523939958", "20261022T072502150851", 4.90)
    original = calibration_store.saved_calibration_path("20261022T072523939958")
    before = original.read_bytes()

    twin_stem = rebuild("20261022T072523939958")
    twin = calibration_store.load_saved_calibration(twin_stem)

    assert twin_stem != "20261022T072523939958"
    assert twin.scale_field.px_per_mm(4000, 3000) == pytest.approx(5.00, rel=1e-6)
    assert twin.rebuilt_from == "20261022T072523939958"
    assert twin.frame_stem == "20261022T072502150851"
    assert original.read_bytes() == before


def test_a_corner_tag_covered_on_the_full_photo_is_saved_and_named(isolated_settings_db, monkeypatch, tmp_path):
    # #349: the preview finds all 4 corner tags, the full-size photo only 3 (tag 455, placed by
    # hand at the bottom left of the photo, the table's SW corner, is covered). The calibration is
    # saved and made current, and the result names the tag and its corner.
    from npec_rig import calibration_run, calibration_store, photo_tags
    from npec_rig.camera import CameraManager

    from tests.web.tag_scenes import CALIBRATION_TAGS, FOUR_CORNER_TAGS

    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    three_corner_tags = [d for d in FOUR_CORNER_TAGS if d.tag_id != 455]

    def detect(frame):
        # The preview is a 4-channel main-stream frame, the full-size photo has 3 channels.
        corner_tags = FOUR_CORNER_TAGS if frame.shape[2] == 4 else three_corner_tags
        return CALIBRATION_TAGS + corner_tags

    monkeypatch.setattr(photo_tags, "detect_tags", detect)
    manager = CameraManager.instance()
    manager.set_lens_position(6.3)
    manager.lock_focus()

    result = calibration_run.run()

    assert "error" not in result
    assert result["warnings"] == [
        "Corner tag 455 cannot be seen in the SW corner of the table. Check that it is not missing or covered."
    ]
    assert calibration_store.load_current_calibration() is not None


def test_with_the_override_a_covered_corner_tag_is_named_from_the_previous_calibration(
    isolated_settings_db, monkeypatch, tmp_path
):
    # #349: the override takes no preview, so the tags of the calibration it replaces say where
    # each corner tag should be. Tag 451, placed by hand at the top right (NE), is covered.
    from npec_rig import calibration_run, photo_tags

    from tests.web.tag_scenes import CALIBRATION_TAGS, FOUR_CORNER_TAGS

    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + FOUR_CORNER_TAGS)
    calibration_run.run(override_focus_gate=True)

    three_corner_tags = [d for d in FOUR_CORNER_TAGS if d.tag_id != 451]
    monkeypatch.setattr(photo_tags, "detect_tags", lambda frame: CALIBRATION_TAGS + three_corner_tags)
    result = calibration_run.run(override_focus_gate=True)

    assert result["warnings"] == [
        "Corner tag 451 cannot be seen in the NE corner of the table. Check that it is not missing or covered."
    ]
