"""A calibration run: the readiness gate, the run itself, and its comparison with the calibration
it replaces (#182).

The rules live here; the routes in routes/calibration.py only call these. The scale field and
install report come from calibration.py, saved calibrations from calibration_store.py, the tags
of each photo from photo_tags.py.

A refused run and a run whose scale field cannot be built are answered, not raised: `run`
returns a result with an `error` field, which the wizard shows next to the Run button.
"""

from datetime import datetime, timezone
from pathlib import Path

from npec_rig import images, photo_tags
from npec_rig.calibration import (
    CalibrationArtifact,
    build_calibration_report,
    build_scale_field,
)
from npec_rig.calibration_store import (
    calibration_frame_path,
    calibration_frame_url,
    load_current_calibration,
    save_calibration,
    stem_for_photo,
)
from npec_rig.camera import CameraManager
from npec_rig.captures import take_photo
from npec_rig.tags import (
    ASSUMED_CALIBRATION_TAG_SIZE_MM,
    CALIBRATION_ID_RANGE,
    CORNER_ID_RANGE,
)
from npec_rig.tripwire import build_corner_baseline

# Calibration's own readiness gate (TODO.md, "Give Lock focus a real function"): all 4 mounted
# corner tags, not check_tripwire's 2-tag minimum -- that check answers "has something changed
# since a good baseline", this one answers "is the camera positioned well enough to calibrate at
# all", which is a stricter bar by design (Aaron, 2026-09-28).
CORNER_TAGS_REQUIRED = 4


def readiness() -> dict:
    """Live check for calibration's own gate: is focus currently locked, and are all 4 corner
    tags currently detectable. Cheap -- a main-stream frame, not a full-res capture -- so it can
    be polled from the wizard, and re-checked by `run` itself right before the expensive capture
    (the backend never trusts a frontend-only check).
    """
    manager = CameraManager.instance()
    focus_locked = manager.focus_status()["locked"]
    frame = manager.capture_array()
    corner_tags_detected = len([d for d in photo_tags.detect_tags(frame) if d.tag_id in CORNER_ID_RANGE])
    return {
        "focus_locked": focus_locked,
        "corner_tags_detected": corner_tags_detected,
        "corner_tags_required": CORNER_TAGS_REQUIRED,
        "ready": focus_locked and corner_tags_detected >= CORNER_TAGS_REQUIRED,
    }


def gate_refusal(ready: dict) -> dict | None:
    """The answer to a run the readiness gate refuses, or None when `ready` passes it."""
    if ready["ready"]:
        return None
    if not ready["focus_locked"]:
        message = "Focus is not confirmed -- confirm focus before running calibration."
    else:
        required = ready["corner_tags_required"]
        message = (
            f"{ready['corner_tags_detected']} of {required} corner tags detected. "
            f"A minimum of {required} is required for a successful calibration."
        )
    return {"error": message, "gate_failed": True, **ready}


def previous_comparison(
    previous: CalibrationArtifact | None,
    *,
    residual_std_pct: float,
    corner_tag_count: int,
    calibration_tag_size_mm: float,
    lens_position: float | None,
    px_per_mm_at_centre: float | None,
    frame_width: int,
    frame_height: int,
) -> dict | None:
    """Compare this run's headline numbers against whatever was the active calibration right
    before this run replaced it (Aaron, 2026-09-28). Cheap, no re-detection: every value here
    already lives on the saved artifact or was just computed for this run's own result -- the
    same caution TODO.md already applies to the history browser (re-detecting tags from every
    saved frame just to show a number is real cost, not a one-line change).
    """
    if previous is None:
        return None

    previous_corner_count = (
        len(previous.corner_baseline.corners_by_id) if previous.corner_baseline else 0
    )
    try:
        previous_px_per_mm = previous.scale_field.px_per_mm(frame_width / 2, frame_height / 2)
    except ValueError:
        previous_px_per_mm = None

    def metric(previous_value: float | None, current_value: float | None) -> dict:
        delta = (
            current_value - previous_value
            if previous_value is not None and current_value is not None
            else None
        )
        return {"previous": previous_value, "current": current_value, "delta": delta}

    return {
        "previous_created_at": previous.created_at,
        "residual_std_pct": metric(previous.scale_field.residual_std_pct, residual_std_pct),
        "corner_tags_detected": metric(previous_corner_count, corner_tag_count),
        "calibration_tag_size_mm": metric(
            previous.calibration_tag_size_mm, calibration_tag_size_mm
        ),
        "lens_position": metric(previous.lens_position, lens_position),
        "px_per_mm_at_centre": metric(previous_px_per_mm, px_per_mm_at_centre),
    }


def run(
    promote: bool = True,
    calibration_tag_size_mm: float | None = None,
    override_focus_gate: bool = False,
) -> dict:
    """Setup calibration (PLAN.md M2 section A): capture a full-res still, detect tags, build the
    scale field and install report, and save the frame plus the resulting artifact.

    `override_focus_gate=True` skips the readiness gate (focus locked, all 4 corner tags
    detected) -- a data-quality check, not a safety one, so it warns rather than refuses outright:
    the operator always has an explicit way through (Aaron, 2026-09-28, see TODO.md's Lock-focus
    entry). Without it, a failed gate returns early with `gate_failed: true` and no capture, so a
    predictably-bad run doesn't cost the ~8.5s full-res round trip.

    Saving the frame, not just the numbers derived from it, matters here: every M2 acceptance
    test (PLAN.md "You verify") is a diff between two calibrations, so a disputed field must be
    re-processable from its original capture without redoing the physical paper-sheet setup.

    `promote=False` (the "set as current baseline" checkbox, unticked) saves this run without
    replacing the active `current.json` -- for a comparison run (the two-baseline/two-height
    tests) taken while a real baseline is still live for `/calibration/tripwire/check` to read.

    `calibration_tag_size_mm`, if given, is the operator's own calliper measurement of *this*
    print run's calibration tags, overriding `ASSUMED_CALIBRATION_TAG_SIZE_MM` -- that constant
    is a placeholder for whoever hasn't measured yet, not a substitute for measuring. A reprint at
    a different size needs a new measurement typed in here, not a source change.
    """
    # Checked before anything below: a refused run (no capture, gate_failed) must have no
    # lasting side effects.
    if not override_focus_gate:
        refusal = gate_refusal(readiness())
        if refusal is not None:
            return refusal

    tag_size_mm = calibration_tag_size_mm if calibration_tag_size_mm is not None else (
        ASSUMED_CALIBRATION_TAG_SIZE_MM
    )

    manager = CameraManager.instance()

    # Captured before this run's own save/promote below can overwrite current.json -- the
    # "previous" half of the post-run comparison.
    previous_artifact = load_current_calibration()

    array, photo = take_photo("calibration")
    frame_height, frame_width = array.shape[0], array.shape[1]

    detections = photo_tags.detect_tags(array)
    calibration_detections = [d for d in detections if d.tag_id in CALIBRATION_ID_RANGE]
    corner_detections = [d for d in detections if d.tag_id in CORNER_ID_RANGE]
    tag_sizes_mm = {d.tag_id: tag_size_mm for d in calibration_detections}

    stem = stem_for_photo(photo)

    result: dict = {
        "calibration_tags_detected": len(calibration_detections),
        "corner_tags_detected": len(corner_detections),
        "calibration_tag_size_mm": tag_size_mm,
        "calibration_tag_size_mm_is_default": calibration_tag_size_mm is None,
        "frame_path": str(calibration_frame_path(stem)),
        # Recorded, not a gate (Aaron, 2026-10-08): the run is promoted as before.
        "photo_flags": photo["flags"],
    }

    try:
        field = build_scale_field(detections, tag_sizes_mm)
    except ValueError as exc:
        result["error"] = str(exc)
        return result
    # The tags this run fitted its scale to, kept as the photo's tags: the diagnostic plots then
    # need no second full-size search of the saved photo, and plot the same tags as the fit.
    images.store_tag_detections(f"{photo['date']}/{Path(photo['filename']).stem}", detections)

    try:
        result["report"] = build_calibration_report(detections, tag_sizes_mm, frame_width, frame_height)
    except ValueError as exc:
        result["report"] = [f"Install report unavailable: {exc}"]
    result["residual_std_pct"] = field.residual_std_pct
    try:
        result["px_per_mm_at_centre"] = field.px_per_mm(frame_width / 2, frame_height / 2)
    except ValueError:
        result["px_per_mm_at_centre"] = None

    try:
        corner_baseline = build_corner_baseline(detections)
    except ValueError:
        corner_baseline = None
    result["corner_baseline_tags"] = sorted(corner_baseline.corners_by_id) if corner_baseline else []

    result["frame_url"] = calibration_frame_url(stem)

    lens_position = manager.get_lens_position()
    result["previous_calibration_comparison"] = previous_comparison(
        previous_artifact,
        residual_std_pct=field.residual_std_pct,
        corner_tag_count=len(corner_baseline.corners_by_id) if corner_baseline else 0,
        calibration_tag_size_mm=tag_size_mm,
        lens_position=lens_position,
        px_per_mm_at_centre=result["px_per_mm_at_centre"],
        frame_width=frame_width,
        frame_height=frame_height,
    )
    artifact = CalibrationArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        scale_field=field,
        corner_baseline=corner_baseline,
        lens_position=lens_position,
        calibration_tag_size_mm=tag_size_mm,
        frame_stem=stem,
    )
    result["artifact_path"] = str(save_calibration(artifact, stem=stem, promote=promote))
    result["promoted_to_current"] = promote
    result["lens_position"] = lens_position
    return result
