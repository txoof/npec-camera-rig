"""Validation of the active calibration: sessions, rounds, and the status line (#182).

The rules that decide whether a round counts, and what the status line says, live here; the
routes in routes/validation.py only call these. Sessions are stored by validation_store.py, the
tags of each photo come from photo_tags.py.

The errors are answered by app.py: ValidationRefusedError 409, RoundNotFoundError and
validation_store.SessionNotFoundError 404.
"""

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from npec_rig import images, photo_tags, validation_store
from npec_rig.calibration import CalibrationArtifact
from npec_rig.calibration_store import load_current_calibration, load_saved_calibration
from npec_rig.camera import CameraBusyError
from npec_rig.captures import CALIBRATION_LENS_TOLERANCE, take_photo
from npec_rig.certainty_map import (
    MIN_MOVED_FRACTION,
    SlotLayoutError,
    build_slot_layout,
    calibration_centres,
    group_sheets,
    moved_fraction,
    round_errors_by_slot,
    slot_layout_from_dict,
    slot_layout_to_dict,
)
from npec_rig.tags import TagDetection


class ValidationRefusedError(Exception):
    """A request the validation rules refuse, with the reason for the operator."""


class RoundNotFoundError(LookupError):
    """No round of that number in the session."""


# One round at a time across the whole app: a round is a full-res capture plus a detection pass,
# and a double-clicked Capture button must not append two rounds from one layout.
_lock = Lock()


def _current_calibration_stem() -> str | None:
    artifact = load_current_calibration()
    return artifact.frame_stem if artifact is not None else None


def focus_problem(focus: dict, artifact: CalibrationArtifact) -> str | None:
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


def summary(session: dict, current_stem: str | None) -> dict:
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


def list_summaries() -> list[dict]:
    """Every validation session, newest first."""
    current_stem = _current_calibration_stem()
    return [summary(s, current_stem) for s in validation_store.list_sessions()]


def get_summary(session_id: str) -> dict:
    return summary(validation_store.load_session(session_id), _current_calibration_stem())


def start() -> dict:
    """A new, empty session against the active calibration. Its tray slots come from the
    calibration frame, and are refused the same way the certainty map refuses them."""
    artifact = load_current_calibration()
    if artifact is None or artifact.frame_stem is None:
        raise ValidationRefusedError("no active calibration with a saved frame to validate")
    layout = slot_layout(artifact)
    with _lock:
        validation_store.end_open_sessions(artifact.frame_stem)
        session = validation_store.new_session(
            artifact.frame_stem, layout["slots"], layout["calibration_centres"]
        )
    return summary(session, artifact.frame_stem)


def slot_layout(artifact: CalibrationArtifact) -> dict:
    """The calibration's tray slots and tag centres, from disk when already worked out. Working
    them out decodes the 64MP calibration frame (about 15 s, the "Start validation" freeze of
    2026-10-02 after a restart emptied the in-memory cache), so the result is saved once."""
    saved = validation_store.load_slot_layout(artifact.frame_stem)
    if saved is not None:
        return saved
    detections = photo_tags.calibration_tags(artifact.frame_stem)
    try:
        layout = build_slot_layout(
            group_sheets(detections, artifact.scale_field, artifact.calibration_tag_size_mm)
        )
    except SlotLayoutError as exc:
        raise ValidationRefusedError(f"this calibration cannot be validated: {exc}") from exc
    slots, centres = slot_layout_to_dict(layout), calibration_centres(detections)
    validation_store.save_slot_layout(artifact.frame_stem, slots, centres)
    return {"slots": slots, "calibration_centres": [list(c) for c in centres]}


def current_session(calibration_stem: str) -> dict | None:
    """The current validation of a calibration: the newest complete one (ROUNDS_REQUIRED rounds
    counted), consistent or not (Aaron, 2026-10-16, #183). A newer validation that is still open,
    or ended early, does not replace it: one started by mistake changes nothing."""
    complete = [
        s
        for s in validation_store.list_sessions()
        if s.get("calibration_stem") == calibration_stem and s.get("completed_at")
    ]
    return max(complete, key=lambda s: s["completed_at"], default=None)


def photo_check(focus: dict) -> dict:
    """Which validation's bands apply to a photo taken now under `focus`, for its sidecar.

    The current validation (`current_session`) of the active calibration, and only when the
    focus lock matches the calibration's lens position (Aaron, 2026-10-09). The photo is flagged
    as not covered when no validation applies, or when the current one is not consistent: a
    not-consistent validation is still named, so the record says which validation the photo was
    taken under, but its bands are not claimed. An unlocked focus is not flagged again here: the
    lens check already says so."""
    artifact = load_current_calibration()
    if artifact is None:
        return {"session": None, "flagged": True, "reason": "no calibration"}
    if focus["lens_position"] is None:
        return {"session": None, "flagged": False, "reason": None}
    problem = focus_problem(focus, artifact)
    if problem:
        return {"session": None, "flagged": True, "reason": problem}
    current = current_session(artifact.frame_stem)
    if current is None:
        return {"session": None, "flagged": True, "reason": "no finished validation of this calibration"}
    session_status = validation_store.status(current)
    if session_status["state"] == "not_consistent":
        reason = f"the validation is {session_status['label'][0].lower()}{session_status['label'][1:]}"
        return {"session": current["id"], "flagged": True, "reason": reason}
    return {"session": current["id"], "flagged": False, "reason": None}


def status(focus: dict) -> dict:
    """Whether the active calibration is validated at the focus lock `focus`, for the Setup and
    Calibration pages. A status, not a block: nothing is refused because of it. Reads the
    session files only, never a capture.

    The current validation (`current_session`), the same one photos are given; the text adds a
    newer validation that is in progress or ended early. With no complete validation yet, the
    newest one's progress."""
    artifact = load_current_calibration()
    if artifact is None:
        return {"state": "no_calibration", "text": "No calibration yet", "session_id": None}
    problem = focus_problem(focus, artifact)
    sessions = [
        s for s in validation_store.list_sessions() if s.get("calibration_stem") == artifact.frame_stem
    ]
    current = current_session(artifact.frame_stem)
    if current is not None:
        session_status, session_id = validation_store.status(current), current["id"]
        state, text = session_status["state"], session_status["label"]
        newer = [
            s for s in sessions if not s.get("completed_at") and s["started_at"] > current["started_at"]
        ]
        if newer:
            text += "; " + _newer_text(newer[0])
    elif not sessions:
        state, text, session_id = "not_validated", "Not validated: no validation of this calibration yet", None
    else:
        session = sessions[0]
        session_status, session_id = validation_store.status(session), session["id"]
        state = session_status["state"]
        if state == "not_validated":
            counted = len(validation_store.counted_rounds(session))
            required = validation_store.ROUNDS_REQUIRED
            if validation_store.is_ended(session):
                text = f"Not validated: the last validation ended after {counted} of {required} rounds"
            else:
                text = f"Not validated: {counted} of {required} rounds counted so far"
        else:
            text = session_status["label"]
    if problem:
        # The validation measured the error at the calibration's lens position, not this one.
        state, text = "focus_mismatch", f"Not validated at this focus: {problem}"
    return {"state": state, "text": text, "session_id": session_id}


def _newer_text(session: dict) -> str:
    """A newer validation that has not completed, for the status line."""
    counted = len(validation_store.counted_rounds(session))
    required = validation_store.ROUNDS_REQUIRED
    if validation_store.is_ended(session):
        text = f"a newer validation ended after {counted} of {required} rounds"
    else:
        text = f"a newer validation is in progress, {counted} of {required} rounds"
    session_status = validation_store.status(session)
    if session_status["state"] == "not_consistent":
        text += f", {session_status['label'][0].lower()}{session_status['label'][1:]}"
    return text


def delete(session_id: str) -> None:
    """Remove one session from history, and the images drawn from it. Its captures stay in the
    gallery."""
    with _lock:
        validation_store.delete_session(session_id)
    images.forget_source(f"validation:{session_id}")


def _refuse_unless_open(session: dict) -> None:
    """Refuse a session that can no longer take rounds."""
    if session["calibration_stem"] != _current_calibration_stem():
        raise ValidationRefusedError(
            "this session's calibration is no longer the active one: start a new session"
        )
    if validation_store.is_ended(session):
        raise ValidationRefusedError("this validation has ended: start a new one")


def capture_round(session_id: str) -> dict:
    """Capture one round, decide whether it counts (`judge_round`) and save it. The capture is
    saved to the gallery either way."""
    if not _lock.acquire(blocking=False):
        raise ValidationRefusedError("a validation round is already being captured")
    try:
        session = validation_store.load_session(session_id)
        _refuse_unless_open(session)
        artifact = load_saved_calibration(session["calibration_stem"])
        try:
            array, record = take_photo("validation", {"validation_session": session_id})
        except CameraBusyError as exc:
            raise ValidationRefusedError(f"camera busy: {exc}") from exc
        del array
        ref = f"{record['date']}/{Path(record['filename']).stem}"
        round_ = judge_round(session, artifact, photo_tags.capture_tags(ref), record, ref)
        session["rounds"].append(round_)
        validation_store.refresh_results(session)
        validation_store.save_session(session)
        return summary(session, session["calibration_stem"])
    finally:
        _lock.release()


def judge_round(
    session: dict,
    artifact: CalibrationArtifact,
    detections: list[TagDetection],
    record: dict,
    ref: str,
) -> dict:
    """The round for capture `ref` (its photo `record` and tag `detections`), and whether it counts.

    Not counted, with the reason, when: focus isn't locked at the calibration's lens position
    (overridable), the photo is flagged as not covered by the bands (overridable), fewer than
    MIN_MOVED_FRACTION of tags moved since the calibration frame and every earlier counted round
    (overridable), or the sheets can't be placed one per tray slot (not overridable: the map
    would pool a sheet into the wrong slot).
    """
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
    problem = focus_problem(record["focus"], artifact)
    reasons = [problem] if problem else []
    # A photo flagged as not covered by the bands is not counted into them either (Aaron,
    # 2026-10-08); the Count anyway override still applies. An unlocked focus is already
    # reported by focus_problem.
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
    return round_


def count_round(session_id: str, index: int) -> dict:
    """Count a round the checks held back, on the operator's say-so (gates need an override).
    Only for reasons the map can still handle: focus, movement and photo flags (lens check,
    cold-start window), never slot placement."""
    with _lock:
        session = validation_store.load_session(session_id)
        if not 0 <= index < len(session["rounds"]):
            raise RoundNotFoundError(f"round {index} not found")
        round_ = session["rounds"][index]
        if round_["counted"]:
            raise ValidationRefusedError("this round already counts")
        if not round_["overridable"]:
            raise ValidationRefusedError(f"this round cannot be counted: {round_['reason']}")
        _refuse_unless_open(session)
        round_["counted"] = True
        round_["overridden"] = True
        validation_store.refresh_results(session)
        validation_store.save_session(session)
        return summary(session, _current_calibration_stem())


def end(session_id: str) -> dict:
    """End a validation: it keeps its rounds and results but takes no more. A validation with
    fewer than the required rounds stays provisional."""
    with _lock:
        session = validation_store.load_session(session_id)
        validation_store.end_session(session)
        validation_store.save_session(session)
        return summary(session, _current_calibration_stem())
