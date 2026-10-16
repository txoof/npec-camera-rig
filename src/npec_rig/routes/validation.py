"""Routes for validation: the Validation page, sessions and their rounds, the status line, and the
maps and problem images."""

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from npec_rig import images, validation_store
from npec_rig.calibration import CalibrationArtifact
from npec_rig.calibration_store import load_current_calibration
from npec_rig.camera import CameraBusyError, CameraManager, array_to_jpeg
from npec_rig.captures import CALIBRATION_LENS_TOLERANCE, take_photo
from npec_rig.certainty_map import (
    MIN_MOVED_FRACTION,
    SlotLayoutError,
    SlotResult,
    build_slot_layout,
    calibration_centres,
    group_sheets,
    moved_fraction,
    render_certainty_map,
    render_problem_frame,
    round_errors_by_slot,
    sheets_by_slot,
    slot_layout_from_dict,
    slot_layout_to_dict,
)
from npec_rig.routes.calibration import (
    _CAPTURE_PREVIEW_WIDTH,
    _calibration_tags,
    _capture_path,
    _capture_tags,
    _load_saved_artifact,
)
from npec_rig.routes.shared import derived_response, templates

router = APIRouter()


@router.get("/setup/validation")
def setup_validation_page(request: Request) -> Response:
    """Validate the active calibration: move the sheets and trays, capture a round, repeat. Runs
    on demand, independent of the calibration wizard."""
    return templates.TemplateResponse(request, "setup_validation.html")


# --- Validation sessions ---
# One round at a time across the whole app: a round is a full-res capture plus a detection pass,
# and a double-clicked Capture button must not append two rounds from one layout.
_validation_lock = Lock()


def _current_calibration_stem() -> str | None:
    artifact = load_current_calibration()
    return artifact.frame_stem if artifact is not None else None


def _focus_problem(focus: dict, artifact: CalibrationArtifact) -> str | None:
    """Why the current focus does not match the calibration's, or None when it does. A
    calibration saved without a lens position is not checked."""
    if not focus.get("locked"):
        return "focus is not locked"
    locked_at = focus.get("lens_position")
    if (
        artifact.lens_position is not None
        and abs(locked_at - artifact.lens_position) > CALIBRATION_LENS_TOLERANCE
    ):
        return (
            f"focus is locked at {locked_at:.2f}, the calibration was taken at "
            f"{artifact.lens_position:.2f}"
        )
    return None


def _session_or_404(session_id: str) -> dict:
    try:
        return validation_store.load_session(session_id)
    except validation_store.SessionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc


def _session_summary(session: dict, current_stem: str | None) -> dict:
    """A session for the UI: everything except the stored per-tag data."""
    counted = validation_store.counted_rounds(session)
    measured = [r["p95_abs_pct"] for r in session["results"] if r["p95_abs_pct"] is not None]
    return {
        "id": session["id"],
        "calibration_stem": session["calibration_stem"],
        "is_current_calibration": session["calibration_stem"] == current_stem,
        "started_at": session["started_at"],
        "completed_at": session["completed_at"],
        "ended_at": session.get("ended_at"),
        "is_open": session["calibration_stem"] == current_stem and not validation_store.is_ended(session),
        "rounds_counted": len(counted),
        "rounds_required": validation_store.ROUNDS_REQUIRED,
        "rounds": [
            {
                **{k: r[k] for k in ("capture", "captured_at", "moved_pct", "counted", "overridden", "reason", "overridable")},
                "slots": validation_store.round_slot_results(r),
            }
            for r in session["rounds"]
        ],
        "results": session["results"],
        "median_range_pct": validation_store.median_ranges(session),
        "median_disagreement_pct": validation_store.MEDIAN_DISAGREEMENT_PCT,
        "inconsistent_slots": validation_store.inconsistent_slots(session),
        "validated": validation_store.is_validated(session),
        "problems": validation_store.round_problems(session),
        "offset_problems": validation_store.offset_problems(session),
        "flagged_slots": validation_store.flagged_slots(session),
        "certainty_range_pct": [min(measured), max(measured)] if measured else None,
        "map_url": f"/validation/sessions/{session['id']}/map" if counted else None,
        "round_span_minutes": validation_store.round_span_minutes(session),
        "short_span": validation_store.short_span(session),
        "min_span_minutes": validation_store.MIN_SPAN_MINUTES,
        "first_counted_at": validation_store.first_last_counted(session)[0],
        "last_counted_at": validation_store.first_last_counted(session)[1],
        # The countdown runs on the Pi's clock, not the browser's (code review).
        "server_time": datetime.now(timezone.utc).isoformat(),
        "min_round_gap_minutes": validation_store.MIN_ROUND_GAP_MINUTES,
        "shortest_gap_minutes": validation_store.shortest_gap_minutes(session),
        "short_gap": validation_store.short_gap(session),
    }


@router.get("/validation/sessions")
def list_validation_sessions() -> list[dict]:
    """Every validation session, newest first."""
    current_stem = _current_calibration_stem()
    return [_session_summary(s, current_stem) for s in validation_store.list_sessions()]


@router.post("/validation/sessions")
def start_validation_session() -> dict:
    """A new, empty session against the active calibration. Its tray slots come from the
    calibration frame, and are refused the same way the certainty map refuses them."""
    artifact = load_current_calibration()
    if artifact is None or artifact.frame_stem is None:
        raise HTTPException(409, "no active calibration with a saved frame to validate")
    layout = _calibration_slot_layout(artifact)
    with _validation_lock:
        validation_store.end_open_sessions(artifact.frame_stem)
        session = validation_store.new_session(
            artifact.frame_stem, layout["slots"], layout["calibration_centres"]
        )
    return _session_summary(session, artifact.frame_stem)


def _calibration_slot_layout(artifact: CalibrationArtifact) -> dict:
    """The calibration's tray slots and tag centres, from disk when already worked out. Working
    them out decodes the 64MP calibration frame (about 15 s, the "Start validation" freeze of
    2026-10-02 after a restart emptied the in-memory cache), so the result is saved once."""
    saved = validation_store.load_slot_layout(artifact.frame_stem)
    if saved is not None:
        return saved
    detections = _calibration_tags(artifact.frame_stem)
    try:
        layout = build_slot_layout(
            group_sheets(detections, artifact.scale_field, artifact.calibration_tag_size_mm)
        )
    except SlotLayoutError as exc:
        raise HTTPException(409, f"this calibration cannot be validated: {exc}") from exc
    slots, centres = slot_layout_to_dict(layout), calibration_centres(detections)
    validation_store.save_slot_layout(artifact.frame_stem, slots, centres)
    return {"slots": slots, "calibration_centres": [list(c) for c in centres]}


@router.get("/validation/status")
def validation_status() -> dict:
    """Whether the active calibration is validated at the current focus lock, for the Setup and
    Calibration pages. A status, not a block: nothing is refused because of it. Reads the
    session files only, never a capture."""
    artifact = load_current_calibration()
    if artifact is None:
        return {"state": "no_calibration", "text": "No calibration yet", "session_id": None}
    focus_problem = _focus_problem(CameraManager.instance().focus_status(), artifact)
    sessions = [
        s for s in validation_store.list_sessions() if s.get("calibration_stem") == artifact.frame_stem
    ]
    if not sessions:
        state, text, session_id = "not_validated", "Not validated: no validation of this calibration yet", None
    else:
        session = sessions[0]
        status, session_id = validation_store.status(session), session["id"]
        state = status["state"]
        if state == "not_validated":
            counted = len(validation_store.counted_rounds(session))
            required = validation_store.ROUNDS_REQUIRED
            if validation_store.is_ended(session):
                text = f"Not validated: the last validation ended after {counted} of {required} rounds"
            else:
                text = f"Not validated: {counted} of {required} rounds counted so far"
        else:
            text = status["label"]
    if focus_problem:
        # The validation measured the error at the calibration's lens position, not this one.
        state, text = "focus_mismatch", f"Not validated at this focus: {focus_problem}"
    return {"state": state, "text": text, "session_id": session_id}


@router.get("/validation/sessions/{session_id}")
def get_validation_session(session_id: str) -> dict:
    return _session_summary(_session_or_404(session_id), _current_calibration_stem())


@router.delete("/validation/sessions/{session_id}")
def delete_validation_session(session_id: str) -> dict:
    """Remove one session from history. Its captures stay in the gallery."""
    with _validation_lock:
        try:
            validation_store.delete_session(session_id)
        except validation_store.SessionNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    images.forget_source(f"validation:{session_id}")
    return {"deleted": session_id}


@router.post("/validation/sessions/{session_id}/rounds")
def capture_validation_round(session_id: str) -> dict:
    """Capture one round and decide whether it counts.

    Not counted, with the reason, when: focus isn't locked at the calibration's lens position
    (overridable), fewer than MIN_MOVED_FRACTION of tags moved since the calibration frame and
    every earlier counted round (overridable), or the sheets can't be placed one per tray slot
    (not overridable: the map would pool a sheet into the wrong slot). The capture is saved to
    the gallery either way.
    """
    if not _validation_lock.acquire(blocking=False):
        raise HTTPException(409, "a validation round is already being captured")
    try:
        session = _session_or_404(session_id)
        if session["calibration_stem"] != _current_calibration_stem():
            raise HTTPException(
                409, "this session's calibration is no longer the active one: start a new session"
            )
        if validation_store.is_ended(session):
            raise HTTPException(409, "this validation has ended: start a new one")
        artifact = _load_saved_artifact(session["calibration_stem"])

        try:
            array, record = take_photo("validation", {"validation_session": session_id})
        except CameraBusyError as exc:
            raise HTTPException(409, f"camera busy: {exc}") from exc
        del array
        focus = record["focus"]
        ref = f"{record['date']}/{Path(record['filename']).stem}"
        detections = _capture_tags(ref)

        round_ = {
            "capture": ref,
            "captured_at": record["timestamp"],
            "moved_pct": None,
            "counted": False,
            "overridden": False,
            "reason": None,
            "overridable": False,
            "slot_errors": None,
            "centres": [list(c) for c in calibration_centres(detections)],
        }
        # Focus is judged first and reported even when the sheets cannot be read: a round at the
        # wrong focus usually finds no sheets at all, and "found 0 calibration sheets" alone sent
        # the operator to the sheets instead of the focus (Aaron, 2026-09-30).
        focus_problem = _focus_problem(focus, artifact)
        reasons = [focus_problem] if focus_problem else []
        # A photo flagged as not covered by the bands is not counted into them either (Aaron,
        # 2026-10-08); the Count anyway override still applies. An unlocked focus is already
        # reported by _focus_problem.
        reasons += [flag for flag in record["flags"] if flag != "focus not locked"]
        try:
            round_["slot_errors"] = round_errors_by_slot(
                detections,
                slot_layout_from_dict(session["slots"]),
                artifact.scale_field,
                artifact.calibration_tag_size_mm,
            )
        except SlotLayoutError as exc:
            round_["reason"] = "; ".join(reasons + [str(exc)])
        else:
            references = [session["calibration_centres"]] + [
                r["centres"] for r in validation_store.counted_rounds(session)
            ]
            moved = moved_fraction(round_["centres"], references, artifact.scale_field)
            round_["moved_pct"] = round(100 * moved, 1)
            if moved < MIN_MOVED_FRACTION:
                reasons.append(
                    f"only {100 * moved:.0f}% of tags moved since the calibration or an earlier "
                    "round: leave the trays where they are and put each sheet on a different tray"
                )
            round_["reason"] = "; ".join(reasons) or None
            round_["overridable"] = bool(reasons)
            round_["counted"] = not reasons

        session["rounds"].append(round_)
        validation_store.refresh_results(session)
        validation_store.save_session(session)
        return _session_summary(session, session["calibration_stem"])
    finally:
        _validation_lock.release()


@router.post("/validation/sessions/{session_id}/rounds/{index}/count")
def count_validation_round(session_id: str, index: int) -> dict:
    """Count a round the checks held back, on the operator's say-so (gates need an override).
    Only for reasons the map can still handle: focus, movement and photo flags (lens check,
    cold-start window), never slot placement."""
    with _validation_lock:
        session = _session_or_404(session_id)
        if not 0 <= index < len(session["rounds"]):
            raise HTTPException(404, f"round {index} not found")
        round_ = session["rounds"][index]
        if round_["counted"]:
            raise HTTPException(409, "this round already counts")
        if not round_["overridable"]:
            raise HTTPException(409, f"this round cannot be counted: {round_['reason']}")
        if session["calibration_stem"] != _current_calibration_stem():
            raise HTTPException(
                409, "this session's calibration is no longer the active one: start a new session"
            )
        if validation_store.is_ended(session):
            raise HTTPException(409, "this validation has ended: start a new one")
        round_["counted"] = True
        round_["overridden"] = True
        validation_store.refresh_results(session)
        validation_store.save_session(session)
        return _session_summary(session, _current_calibration_stem())


@router.post("/validation/sessions/{session_id}/end")
def end_validation_session(session_id: str) -> dict:
    """End a validation: it keeps its rounds and results but takes no more. A validation with
    fewer than the required rounds stays provisional."""
    with _validation_lock:
        session = _session_or_404(session_id)
        validation_store.end_session(session)
        validation_store.save_session(session)
        return _session_summary(session, _current_calibration_stem())


@router.get("/validation/sessions/{session_id}/map")
def validation_session_map(session_id: str) -> Response:
    """The session's certainty map: pooled per-slot results from the stored rounds, drawn on the
    latest counted capture. Made once per distinct content and kept (images.py), so it is served
    from disk afterwards, also after a restart."""
    session = _session_or_404(session_id)
    counted = validation_store.counted_rounds(session)
    if not counted:
        raise HTTPException(409, "no rounds count yet")
    status = validation_store.status(session)["label"]
    caption = (
        f"{status}. Calibration {session['calibration_stem']}, {len(counted)} round(s) pooled. "
        "95% of tags within the stated band, at tray-top height."
    )
    inputs = {
        "capture": counted[-1]["capture"],
        "preview_width": _CAPTURE_PREVIEW_WIDTH,
        "slots": session["slots"],
        "results": session["results"],
        "caption": caption,
    }
    return derived_response("validation_map", f"validation:{session_id}", inputs)


def _render_validation_map(inputs: dict) -> bytes:
    preview, scale = images.reduced_frame(_capture_path(inputs["capture"]), inputs["preview_width"])
    results = [
        SlotResult(r["name"], r["n"], r["p95_abs_pct"], r["median_pct"]) for r in inputs["results"]
    ]
    image = render_certainty_map(
        preview, slot_layout_from_dict(inputs["slots"]), results, inputs["caption"], frame_scale=scale
    )
    return array_to_jpeg(image)


def _size_text(offset_pct: float) -> str:
    return f"{abs(offset_pct):.1f}% {'small' if offset_pct < 0 else 'large'}"


@router.get("/validation/sessions/{session_id}/rounds/{number}/problems")
def validation_round_problems_image(session_id: str, number: int) -> Response:
    """Round `number`'s full frame (1-based, as the page counts rounds) with a red border around
    each sheet `validation_store.round_problems` names in it, where that sheet sat in that round,
    or around the whole frame for a whole-round shift."""
    session = _session_or_404(session_id)
    problems = [p for p in validation_store.round_problems(session) if p["round"] == number]
    if not problems:
        raise HTTPException(404, f"round {number} has no problems")
    whole = [p for p in problems if p["slot"] is None]
    if whole:
        caption = (
            f"Round {number}: every slot reads about {_size_text(whole[0]['offset_pct'])} compared "
            "with other rounds. Check whether the camera or the table moved."
        )
    else:
        caption = (
            f"Round {number}. Red: the sheet or tray that reads differently from other rounds. "
            "Check the sheet with callipers and the tray height."
        )
    return _problem_frame_response(session, session["rounds"][number - 1], problems, caption)


@router.get("/validation/sessions/{session_id}/offsets")
def validation_offsets_image(session_id: str) -> Response:
    """The latest counted round's full frame with a red border around each slot that reads
    steadily off the others (`validation_store.offset_problems`), or around the whole frame when
    every slot reads off since the calibration."""
    session = _session_or_404(session_id)
    problems = validation_store.offset_problems(session)
    if not problems:
        raise HTTPException(404, "no slot reads steadily off")
    whole = [p for p in problems if p["slot"] is None]
    if whole:
        caption = (
            f"Every slot reads about {_size_text(whole[0]['offset_pct'])} in every round compared "
            "with the calibration. Check whether the camera or the table moved, then recalibrate."
        )
    else:
        caption = (
            "Red: reads differently from the other slots in every round. Check the sheet with "
            "callipers, the tray height, and the slot."
        )
    return _problem_frame_response(session, validation_store.counted_rounds(session)[-1], problems, caption)


def _problem_frame_response(session: dict, round_: dict, problems: list[dict], caption: str) -> Response:
    """`round_`'s full frame, a red border around each named slot's sheet where it sat in that
    round, or around the whole frame for a problem with no slot."""
    artifact = _load_saved_artifact(session["calibration_stem"])
    detections = _capture_tags(round_["capture"])  # for the sheet boxes; the image is reduced
    placed = sheets_by_slot(
        group_sheets(detections, artifact.scale_field, artifact.calibration_tag_size_mm),
        slot_layout_from_dict(session["slots"]),
    )
    named = [p for p in problems if p["slot"] is not None]
    inputs = {
        "capture": round_["capture"],
        "preview_width": _CAPTURE_PREVIEW_WIDTH,
        "boxes": {p["slot"]: list(placed[p["slot"]].box) for p in named},
        "labels": {p["slot"]: f"{p['slot']}: reads {_size_text(p['offset_pct'])}" for p in named},
        "caption": caption,
        "whole_frame": any(p["slot"] is None for p in problems),
    }
    return derived_response("problem_frame", f"validation:{session['id']}", inputs)


def _render_problem_frame(inputs: dict) -> bytes:
    preview, scale = images.reduced_frame(_capture_path(inputs["capture"]), inputs["preview_width"])
    boxes = {name: tuple(box) for name, box in inputs["boxes"].items()}
    image = render_problem_frame(
        preview, boxes, inputs["labels"], inputs["caption"], whole_frame=inputs["whole_frame"],
        frame_scale=scale,
    )
    return array_to_jpeg(image)


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
images.register(images.Recipe("validation_map", 1, _render_validation_map))
images.register(images.Recipe("problem_frame", 1, _render_problem_frame))
