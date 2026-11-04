"""The tray randomization page (#343): suggest a random layout of the trays for the running
experiment, then check a new photo against it, with an overlay that shows where each tray that is
out of place goes and which trays to turn.

Its own page for now; later part of a Status page with the running experiment (Aaron,
2026-11-04).
"""

from __future__ import annotations

import random
import secrets
from datetime import UTC, datetime

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from npec_rig import database, images
from npec_rig.camera import CameraBusyError, array_to_jpeg
from npec_rig.captures import photo_file, take_photo
from npec_rig.randomization import (
    LayoutUnreadableError,
    NoLayoutError,
    Position,
    check_layout,
    exposure,
    photo_layout,
    suggest_layout,
    tray_type,
)
from npec_rig.routes.shared import derived_response, templates
from npec_rig.text_render import text_layer, text_width

router = APIRouter()

# The overlay's width in pixels: the gallery's screen copy.
OVERLAY_WIDTH = 1600


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _running() -> dict:
    experiment = database.running_experiment()
    if experiment is None:
        raise HTTPException(409, "No experiment is running. Start one on the Experiments page.")
    return experiment


def _columns(slots: list[str]) -> int:
    return max(int(slot.split()[1]) for slot in slots)


def _where(tray_id: int, position: Position | None, columns: int) -> dict | None:
    """A position as saved: slot, heading and the rows and columns it puts on an outside edge
    (None when the heading is not read)."""
    if position is None or position.slot is None:
        return None
    edges = exposure(tray_id, position, columns)
    return {"slot": position.slot, "heading": position.heading, "edges": None if edges is None else sorted(edges)}


def _references(experiment_id: int) -> dict[int, float]:
    """Each 2 x 2 tray's tag angle in its first photo, as the latest suggestion kept them."""
    latest = database.latest_tray_layout(experiment_id, "suggestion")
    if latest is None:
        return {}
    return {int(k): v for k, v in latest["details"].get("references", {}).items()}


def _latest_photo(experiment_id: int) -> dict | None:
    """The newest photo of the table: the experiment's latest still, or the latest check's photo
    when that is newer. Where each tray lies now is read from it."""
    stills = database.captures_for_experiment(experiment_id)
    still = stills[-1] if stills else None
    check = database.latest_tray_layout(experiment_id, "check")
    if check is not None and (still is None or check["details"]["taken_at"] > still["taken_at"]):
        return {"id": check["capture_id"], "path": check["details"]["photo"], "taken_at": check["details"]["taken_at"]}
    return None if still is None else {"id": still["id"], "path": still["path"], "taken_at": still["taken_at"]}


@router.get("/randomize", response_class=HTMLResponse)
def randomize_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "randomize.html")


@router.get("/api/randomize")
def randomize_state() -> dict:
    """The running experiment, its latest suggestion and its latest check (None where none)."""
    experiment = database.running_experiment()
    if experiment is None:
        return {"experiment": None, "suggestion": None, "check": None}
    suggestion = database.latest_tray_layout(experiment["id"], "suggestion")
    check = database.latest_tray_layout(experiment["id"], "check")
    if check is not None and suggestion is not None and check["suggestion_id"] != suggestion["id"]:
        check = None  # a check of an older suggestion says nothing about this one
    return {
        "experiment": {"id": experiment["id"], "name": experiment["name"]},
        "suggestion": _suggestion_out(suggestion),
        "check": _check_out(check),
    }


def _suggestion_out(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {"id": row["id"], "experiment_id": row["experiment_id"], "made_at": row["made_at"], **row["details"]}


def _check_out(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "suggestion_id": row["suggestion_id"],
        "made_at": row["made_at"],
        "overlay": f"/api/randomize/checks/{row['id']}/overlay",
        **row["details"],
    }


@router.post("/api/randomize/suggest")
def suggest() -> dict:
    """Suggest a random layout of the trays on the table now (read from the newest photo), drawn
    by restricted randomization against where each tray lies now, and save it with the
    experiment."""
    experiment = _running()
    photo = _latest_photo(experiment["id"])
    if photo is None:
        raise HTTPException(409, "The experiment has no photo yet: take one, then suggest a layout.")
    references = _references(experiment["id"])
    try:
        seen, slots = photo_layout(photo["path"], references)
    except LayoutUnreadableError as exc:
        raise HTTPException(409, f"Cannot read where the trays are: {exc}.") from exc
    names = [slot["name"] for slot in slots]
    columns = _columns(names)
    last = {t.tray_id: Position(t.slot, t.heading) for t in seen if t.slot is not None}
    # A 2 x 2 tray seen for the first time: this photo's angle is its reference from now on.
    for t in seen:
        if tray_type(t.tray_id).name == "2x2":
            references.setdefault(t.tray_id, round(t.tag_angle, 2))
    if not last:
        raise HTTPException(409, "No tray was found in a slot in the latest photo.")
    seed = secrets.randbits(32)
    try:
        layout = suggest_layout(sorted(last), last, names, random.Random(seed))
    except NoLayoutError as exc:
        raise HTTPException(409, "No layout keeps every edge row off the edge this round.") from exc
    details = {
        "seed": seed,
        "photo": photo["path"],
        "taken_at": photo["taken_at"],
        "references": {str(k): v for k, v in sorted(references.items())},
        "trays": [
            {
                "tray_id": tray,
                "tray_type": tray_type(tray).name,
                **_where(tray, position, columns),
                "last": _where(tray, last[tray], columns),
                # Turn the tray round from how it lies now; None when its heading is not read.
                "turn": None if position.heading is None or last[tray].heading is None
                else position.heading != last[tray].heading,
            }
            for tray, position in sorted(layout.items())
        ],
    }
    row = database.record_tray_layout(
        experiment["id"], "suggestion", made_at=_now(), details=details, capture_id=photo["id"]
    )
    return _suggestion_out(row)


@router.post("/api/randomize/check")
def check() -> dict:
    """Take a new photo (a rig photo, not one of the experiment's stills) and compare where each
    tray lies in it with the latest suggestion; save the result with the experiment."""
    experiment = _running()
    suggestion = database.latest_tray_layout(experiment["id"], "suggestion")
    if suggestion is None:
        raise HTTPException(409, "There is no suggested layout to check against: press Suggest first.")
    try:
        _array, record = take_photo("layout check")
    except CameraBusyError as exc:
        raise HTTPException(409, "The camera is busy taking another photo. Try again in a minute.") from exc
    del _array  # a 64MP frame is about 190 MB
    references = {int(k): v for k, v in suggestion["details"].get("references", {}).items()}
    try:
        seen, slots = photo_layout(record["path"], references)
    except LayoutUnreadableError as exc:
        raise HTTPException(409, f"Cannot read where the trays are: {exc}.") from exc
    columns = _columns([slot["name"] for slot in slots])
    trays = suggestion["details"]["trays"]
    wanted = {t["tray_id"]: Position(t["slot"], t["heading"]) for t in trays}
    last = {t["tray_id"]: Position(t["last"]["slot"], t["last"]["heading"]) for t in trays if t["last"]}
    checks = check_layout(wanted, seen, last, columns)
    details = {
        "photo": record["path"],
        "taken_at": record["timestamp"],
        "slots": [{"name": s["name"], "centre": s["centre"], "box": s["box"]} for s in slots],
        "trays": [
            {
                "tray_id": c.tray_id,
                "status": c.status,
                "tray_type": tray_type(c.tray_id).name,
                "wanted": _where(c.tray_id, c.wanted, columns),
                "found": _where(c.tray_id, c.found, columns),
                "centre": None if c.centre is None else [round(v, 1) for v in c.centre],
                "breaks_rule": c.breaks_rule,
            }
            for c in checks
        ],
    }
    row = database.record_tray_layout(
        experiment["id"], "check", made_at=_now(), details=details,
        capture_id=record["capture_id"], suggestion_id=suggestion["id"],
    )
    return _check_out(row)


@router.get("/api/randomize/checks/{check_id}/overlay")
def check_overlay(check_id: int) -> Response:
    """The check's photo at the screen copy's size, with an arrow from each tray in the wrong slot
    to the slot it goes to, a turning arrow on each tray to turn, and a word on every tray."""
    row = database.tray_layout(check_id)
    if row is None or row["kind"] != "check":
        raise HTTPException(404, f"no layout check {check_id}")
    details = row["details"]
    inputs = {"photo": details["photo"], "width": OVERLAY_WIDTH, "slots": details["slots"], "trays": details["trays"]}
    return derived_response("randomize_check", details["photo"], inputs)


# RGB. Every mark also carries words, never colour alone.
_OK_COLOUR = (40, 220, 90)  # green
_MOVE_COLOUR = (255, 150, 0)  # orange
_TURN_COLOUR = (255, 0, 255)  # magenta, apart from the blue trays and green leaves
_PROBLEM_COLOUR = (255, 60, 60)  # red
_SLOT_COLOUR = (230, 230, 230)


def _label(status: str, tray: dict) -> tuple[list[str], tuple[int, int, int]]:
    """The words written on a tray, and their colour: two short lines, so neighbours do not
    run into each other. Whether a tray breaks the edge rule is in the page's table."""
    name = f"Tray {tray['tray_id']}"
    slot = tray["wanted"] and tray["wanted"]["slot"]
    return {
        "in place": ([f"{name} OK"], _OK_COLOUR),
        "wrong slot": ([name, f"to {slot}"], _MOVE_COLOUR),
        "wrong slot, turned": ([name, f"to {slot}, turn"], _MOVE_COLOUR),
        "turned": ([name, "turn 180"], _TURN_COLOUR),
        "heading not read": ([name, "heading?"], _PROBLEM_COLOUR),
        "not in layout": ([name, "not in layout"], _PROBLEM_COLOUR),
        "not placed": ([name, "no slot"], _PROBLEM_COLOUR),
        "missing": ([f"{name} missing"], _PROBLEM_COLOUR),
    }[status]


def _turn_arrow(image: np.ndarray, centre: tuple[int, int], radius: int, colour) -> None:
    """A circular arrow around `centre`: turn the tray round."""
    cv2.ellipse(image, centre, (radius, radius), 0, -60, 220, colour, 6, cv2.LINE_AA)
    end = np.radians(220)
    tip = (centre[0] + radius * np.cos(end), centre[1] + radius * np.sin(end))
    # The head points along the arc's direction at its end (angles grow clockwise on screen).
    tangent = (-np.sin(end), np.cos(end))
    tail = (tip[0] - 40 * tangent[0], tip[1] - 40 * tangent[1])
    cv2.arrowedLine(image, (round(tail[0]), round(tail[1])), (round(tip[0]), round(tip[1])), colour, 6, cv2.LINE_AA, tipLength=1.0)


def _render_check_overlay(inputs: dict) -> bytes:
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, scale = images.reduced_frame(found, inputs["width"])
    slot_centre = {s["name"]: np.array(s["centre"]) * scale for s in inputs["slots"]}
    labels = []
    for tray in inputs["trays"]:
        status = tray["status"]
        lines, colour = _label(status, tray)
        if tray["centre"] is not None:
            centre = np.array(tray["centre"]) * scale
        elif tray["wanted"] is not None:
            centre = slot_centre[tray["wanted"]["slot"]]
        else:
            continue
        x, y = (round(v) for v in centre)
        if status == "in place":
            cv2.circle(image, (x, y), 40, colour, 6, cv2.LINE_AA)
        elif status == "missing":
            cv2.drawMarker(image, (x, y), colour, cv2.MARKER_TILTED_CROSS, 80, 6, cv2.LINE_AA)
        if status.startswith("wrong slot") and tray["wanted"] is not None:
            tx, ty = (round(v) for v in slot_centre[tray["wanted"]["slot"]])
            cv2.arrowedLine(image, (x, y), (tx, ty), (0, 0, 0), 14, cv2.LINE_AA, tipLength=0.08)
            cv2.arrowedLine(image, (x, y), (tx, ty), colour, 8, cv2.LINE_AA, tipLength=0.08)
        if status in ("turned", "wrong slot, turned"):
            _turn_arrow(image, (x, y), 70, _TURN_COLOUR)
        labels.append(((x, y + 100), lines, colour))
    with text_layer(image) as layer:
        for (x, y), lines, colour in labels:
            for i, line in enumerate(lines):
                half = text_width(line, 0.7) / 2 + 3
                lx = round(min(max(x, half), image.shape[1] - half))
                layer.text(line, (lx, y + 25 * i), 0.7, colour, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
        for name, (sx, sy) in slot_centre.items():
            layer.text(name, (round(sx), round(sy) - 120), 0.6, _SLOT_COLOUR, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
    return array_to_jpeg(image)


# Bump the version whenever the renderer would draw the same inputs differently.
images.register(images.Recipe("randomize_check", 2, _render_check_overlay))
