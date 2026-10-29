"""Routes for validation: the Validation page, sessions and their rounds, the status line, and the
maps and problem images."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from npec_rig import images, photo_tags, validation, validation_store
from npec_rig.calibration_store import load_saved_calibration
from npec_rig.camera import CameraManager, array_to_jpeg
from npec_rig.certainty_map import (
    SlotResult,
    group_sheets,
    render_certainty_map,
    render_problem_frame,
    sheets_by_slot,
    slot_layout_from_dict,
)
from npec_rig.routes.shared import derived_response, templates

router = APIRouter()


@router.get("/setup/validation")
def setup_validation_page(request: Request) -> Response:
    """Validate the active calibration: move the sheets and trays, capture a round, repeat. Runs
    on demand, independent of the calibration wizard."""
    return templates.TemplateResponse(request, "setup_validation.html")


# --- Validation sessions ---
# The rules are in validation.py; app.py answers its errors.


@router.get("/validation/sessions")
def list_validation_sessions() -> list[dict]:
    """Every validation session, newest first."""
    return validation.list_summaries()


@router.post("/validation/sessions")
def start_validation_session() -> dict:
    """A new, empty session against the active calibration."""
    return validation.start()


@router.get("/validation/status")
def validation_status() -> dict:
    """Whether the active calibration is validated at the current focus lock, for the Setup and
    Calibration pages."""
    return validation.status(CameraManager.instance().focus_status())


@router.get("/validation/sessions/{session_id}")
def get_validation_session(session_id: str) -> dict:
    return validation.get_summary(session_id)


@router.delete("/validation/sessions/{session_id}")
def delete_validation_session(session_id: str) -> dict:
    """Remove one session from history. Its captures stay in the gallery."""
    validation.delete(session_id)
    return {"deleted": session_id}


@router.post("/validation/sessions/{session_id}/rounds")
def capture_validation_round(session_id: str) -> dict:
    """Capture one round and decide whether it counts (validation.judge_round)."""
    return validation.capture_round(session_id)


@router.post("/validation/sessions/{session_id}/rounds/{index}/count")
def count_validation_round(session_id: str, index: int) -> dict:
    """Count a round the checks held back, on the operator's say-so."""
    return validation.count_round(session_id, index)


class DiscardRequest(BaseModel):
    reason: str


@router.post("/validation/sessions/{session_id}/rounds/{index}/discard")
def discard_validation_round(session_id: str, index: int, request: DiscardRequest) -> dict:
    """Stop counting a round, with the operator's reason; Count it anyway undoes it."""
    return validation.discard_round(session_id, index, request.reason)


@router.post("/validation/sessions/{session_id}/end")
def end_validation_session(session_id: str) -> dict:
    """End a validation: it keeps its rounds and results but takes no more."""
    return validation.end(session_id)


@router.get("/validation/sessions/{session_id}/map")
def validation_session_map(session_id: str) -> Response:
    """The session's certainty map: pooled per-slot results from the stored rounds, drawn on the
    latest counted capture. Made once per distinct content and kept (images.py), so it is served
    from disk afterwards, also after a restart."""
    session = validation_store.load_session(session_id)
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
        "preview_width": photo_tags.PREVIEW_WIDTH,
        "slots": session["slots"],
        "results": session["results"],
        "caption": caption,
    }
    return derived_response("validation_map", f"validation:{session_id}", inputs)


def _render_validation_map(inputs: dict) -> bytes:
    preview, scale = images.reduced_frame(photo_tags.capture_path(inputs["capture"]), inputs["preview_width"])
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
    session = validation_store.load_session(session_id)
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
    session = validation_store.load_session(session_id)
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
    artifact = load_saved_calibration(session["calibration_stem"])
    detections = photo_tags.capture_tags(round_["capture"])  # for the sheet boxes; the image is reduced
    placed = sheets_by_slot(
        group_sheets(detections, artifact.scale_field, artifact.calibration_tag_size_mm),
        slot_layout_from_dict(session["slots"]),
        artifact.scale_field,
    )
    named = [p for p in problems if p["slot"] is not None]
    inputs = {
        "capture": round_["capture"],
        "preview_width": photo_tags.PREVIEW_WIDTH,
        "boxes": {p["slot"]: list(placed[p["slot"]].box) for p in named},
        "labels": {p["slot"]: f"{p['slot']}: reads {_size_text(p['offset_pct'])}" for p in named},
        "caption": caption,
        "whole_frame": any(p["slot"] is None for p in problems),
    }
    return derived_response("problem_frame", f"validation:{session['id']}", inputs)


def _render_problem_frame(inputs: dict) -> bytes:
    preview, scale = images.reduced_frame(photo_tags.capture_path(inputs["capture"]), inputs["preview_width"])
    boxes = {name: tuple(box) for name, box in inputs["boxes"].items()}
    image = render_problem_frame(
        preview, boxes, inputs["labels"], inputs["caption"], whole_frame=inputs["whole_frame"],
        frame_scale=scale,
    )
    return array_to_jpeg(image)


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
images.register(images.Recipe("validation_map", 1, _render_validation_map))
images.register(images.Recipe("problem_frame", 1, _render_problem_frame))
