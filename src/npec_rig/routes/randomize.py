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

from npec_rig import database, images, photo_tags
from npec_rig.photo_tags import CaptureNotFoundError, CaptureRefError
from npec_rig.camera import CameraBusyError, array_to_jpeg
from npec_rig.captures import photo_file, take_photo
from npec_rig.randomization import (
    LayoutUnreadableError,
    Lying,
    NoLayoutError,
    Place,
    Position,
    breaks_rule,
    check_layout,
    exposure,
    least_breaking_layout,
    photo_layout,
    suggest_layout,
    tray_type,
)
from npec_rig.routes.shared import derived_response, templates
from npec_rig.tags import grayscale_uint8
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


def _edges(tray_id: int, lying: Lying | None) -> list[str] | None:
    edges = exposure(tray_id, lying)
    return None if edges is None else sorted(edges)


def _places(details: dict) -> dict[str, Place]:
    return {
        p["name"]: Place(p["name"], tuple(p["centre"]), frozenset(p["sides"]), p["px_per_mm"], p["label"], p["occupant"])
        for p in details["places"]
    }


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


def _round(experiment_id: int) -> tuple[dict | None, dict | None, dict | None]:
    """(the suggestion being worked on, its latest check, the check that finished the last round).

    The page starts as the trays stand (Aaron, 2026-11-04): a suggestion is worked on from
    Randomize until it is cancelled or a check finds every tray in place, which ends the round."""
    suggestion = database.latest_tray_layout(experiment_id, "suggestion")
    if suggestion is None or database.latest_tray_layout_for(suggestion["id"], "cancel") is not None:
        return None, None, None
    check = database.latest_tray_layout_for(suggestion["id"], "check")
    if check is not None and all(t["status"] == "in place" for t in check["details"]["trays"]):
        return None, None, check
    return suggestion, check, None


@router.get("/api/randomize")
def randomize_state() -> dict:
    """The running experiment, the suggestion being worked on and its latest check (None where
    none), and the check that ended the last round when every tray was found in place."""
    experiment = database.running_experiment()
    if experiment is None:
        return {"experiment": None, "suggestion": None, "check": None, "finished": None}
    suggestion, check, finished = _round(experiment["id"])
    return {
        "experiment": {"id": experiment["id"], "name": experiment["name"]},
        "suggestion": _suggestion_out(suggestion),
        "check": _check_out(check),
        "finished": _check_out(finished),
    }


@router.post("/api/randomize/cancel")
def cancel() -> dict:
    """Stop working on the suggestion: the page goes back to the trays as they stand. The
    suggestion and its checks stay saved, with the cancelling."""
    experiment = _running()
    suggestion, _check, _finished = _round(experiment["id"])
    if suggestion is None:
        raise HTTPException(409, "There is no suggested layout to cancel.")
    database.record_tray_layout(
        experiment["id"], "cancel", made_at=_now(), details={}, suggestion_id=suggestion["id"]
    )
    return {"cancelled": suggestion["id"]}


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
    """Suggest a random layout of the trays on the table now, read from the newest photo: the
    places are where the trays stand in it (Aaron, 2026-11-04), shuffled by restricted
    randomization against how each tray lies now. Saved with the experiment."""
    experiment = _running()
    photo = _latest_photo(experiment["id"])
    if photo is None:
        raise HTTPException(409, "The experiment has no photo yet: take one, then suggest a layout.")
    references = _references(experiment["id"])
    previous = database.latest_tray_layout(experiment["id"], "suggestion")
    known = [tuple(p["centre"]) for p in previous["details"]["places"]] if previous else []
    try:
        seen, photo_places, _scale = photo_layout(photo["path"], references, known)
    except (LayoutUnreadableError, CaptureNotFoundError, CaptureRefError) as exc:
        raise HTTPException(409, f"Cannot read where the trays are: {exc}.") from exc
    finally:
        # A still not yet read by the tray reader is searched for tags at full size here (#348).
        images.release_freed_memory()
    if not seen:
        raise HTTPException(409, "No tray with a tag was found in the latest photo.")
    # The places the trays make, empty ones too: the empty spots move as well (Aaron, 2026-11-04).
    places = {p.name: p for p in photo_places}
    standing_in = {p.occupant: p.name for p in photo_places if p.occupant is not None}
    last = {t.tray_id: Lying(t.sides, t.heading) for t in seen}
    # A 2 x 2 tray seen for the first time: this photo's angle is its reference from now on.
    for t in seen:
        if tray_type(t.tray_id).name == "2x2":
            references.setdefault(t.tray_id, round(t.tag_angle, 2))
    seed = secrets.randbits(32)
    rng, sides = random.Random(seed), {n: p.sides for n, p in places.items()}
    try:
        layout, rule_kept = suggest_layout(sorted(last), last, sides, rng), True
    except NoLayoutError:
        # Every layout repeats an edge row somewhere (a tray with both the north and south
        # borders, say): give the one that repeats fewest, with those trays marked.
        layout, rule_kept = least_breaking_layout(sorted(last), last, sides, rng), False
    details = {
        "seed": seed,
        "rule_kept": rule_kept,
        "photo": photo["path"],
        "taken_at": photo["taken_at"],
        "references": {str(k): v for k, v in sorted(references.items())},
        "places": [
            {"name": p.name, "label": p.label, "occupant": p.occupant, "centre": [round(v, 1) for v in p.centre],
             "sides": sorted(p.sides), "px_per_mm": round(p.px_per_mm, 4)}
            for p in places.values()
        ],
        "trays": [
            {
                "tray_id": tray,
                "tray_type": tray_type(tray).name,
                "place": position.place,
                "place_label": places[position.place].label,
                "heading": position.heading,
                "edges": _edges(tray, Lying(places[position.place].sides, position.heading)),
                "last": {"place": standing_in[tray], "place_label": places[standing_in[tray]].label,
                         "heading": last[tray].heading, "sides": sorted(last[tray].sides), "edges": _edges(tray, last[tray])},
                "breaks_rule": breaks_rule(last[tray], Lying(places[position.place].sides, position.heading), tray),
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
    tray stands in it with the latest suggestion; save the result with the experiment."""
    experiment = _running()
    suggestion, _check, _finished = _round(experiment["id"])
    if suggestion is None:
        raise HTTPException(409, "There is no suggested layout to check against: press Randomize first.")
    try:
        frame, record = take_photo("layout check")
    except CameraBusyError as exc:
        raise HTTPException(409, "The camera is busy taking another photo. Try again in a minute.") from exc
    # The photo's tags are searched on the frame just taken, not on its saved JPEG decoded again:
    # that decode is the largest step (about 0.6 GB, metrology log 25.2). As the tag search does
    # (#348): the grey copy first, the colour frame (about 190 MB) freed before the slot is
    # waited for, the search in the full-size slot, the tags stored for the photo.
    gray = grayscale_uint8(frame)
    del frame
    images.release_freed_memory()
    details = suggestion["details"]
    references = {int(k): v for k, v in details.get("references", {}).items()}
    try:
        with images.full_decode_slot():
            detections = photo_tags.detect_tags(gray)
        del gray
        images.store_tag_detections(record["path"].removeprefix("rig/"), detections)
        seen, _check_places, _scale = photo_layout(record["path"], references)
    except (LayoutUnreadableError, CaptureNotFoundError, CaptureRefError) as exc:
        raise HTTPException(409, f"Cannot read where the trays are: {exc}.") from exc
    finally:
        images.release_freed_memory()
    places = _places(details)
    wanted = {t["tray_id"]: Position(t["place"], t["heading"]) for t in details["trays"]}
    last = {t["tray_id"]: Lying(frozenset(t["last"]["sides"]), t["last"]["heading"]) for t in details["trays"]}
    checks = check_layout(wanted, seen, last, places)
    out = {
        "photo": record["path"],
        "taken_at": record["timestamp"],
        "places": details["places"],
        "trays": [
            {
                "tray_id": c.tray_id,
                "tray_type": tray_type(c.tray_id).name,
                "status": c.status,
                "wanted": None if c.wanted is None else {
                    "place": c.wanted.place, "label": places[c.wanted.place].label, "heading": c.wanted.heading},
                "found_at": c.found_at,
                "heading": c.heading,
                "centre": None if c.centre is None else [round(v, 1) for v in c.centre],
                "edges": None if c.sides is None else _edges(c.tray_id, Lying(c.sides, c.heading)),
                "breaks_rule": c.breaks_rule,
            }
            for c in checks
        ],
    }
    row = database.record_tray_layout(
        experiment["id"], "check", made_at=_now(), details=out,
        capture_id=record["capture_id"], suggestion_id=suggestion["id"],
    )
    return _check_out(row)


@router.get("/api/randomize/checks/{check_id}/overlay")
def check_overlay(check_id: int) -> Response:
    """The check's photo at the screen copy's size, with an arrow from each tray in the wrong place
    to the place it goes to, a turning arrow on each tray to turn, and a word on every tray."""
    row = database.tray_layout(check_id)
    if row is None or row["kind"] != "check":
        raise HTTPException(404, f"no layout check {check_id}")
    details = row["details"]
    inputs = {"photo": details["photo"], "width": OVERLAY_WIDTH, "places": details["places"], "trays": details["trays"]}
    return derived_response("randomize_check", details["photo"], inputs)


# RGB. Every mark also carries words, never colour alone.
_OK_COLOUR = (40, 220, 90)  # green
_MOVE_COLOUR = (255, 150, 0)  # orange
_TURN_COLOUR = (255, 0, 255)  # magenta, apart from the blue trays and green leaves
_PROBLEM_COLOUR = (255, 60, 60)  # red
_PLACE_COLOUR = (240, 240, 240)  # white rings: where a tray goes


def _label(status: str, tray: dict) -> tuple[list[str], tuple[int, int, int]]:
    """The words written on a tray, and their colour: two short lines, so neighbours do not
    run into each other. Whether a tray breaks the edge rule is in the page's table."""
    name = f"Tray {tray['tray_id']}"
    return {
        "in place": ([f"{name} OK"], _OK_COLOUR),
        "wrong place": ([name, "move"], _MOVE_COLOUR),
        "wrong place, turned": ([name, "move, turn"], _MOVE_COLOUR),
        "turned": ([name, "turn 180"], _TURN_COLOUR),
        "heading not read": ([name, "heading?"], _PROBLEM_COLOUR),
        "not in layout": ([name, "not in layout"], _PROBLEM_COLOUR),
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
    """Each tray in the wrong place gets an arrow to a white ring marked "Tray N goes here" where
    it goes; each tray to turn a turning arrow; each tray in place a green circle and "OK"."""
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, scale = images.reduced_frame(found, inputs["width"])
    place_centre = {p["name"]: np.array(p["centre"]) * scale for p in inputs["places"]}
    labels, rings = [], []
    for tray in inputs["trays"]:
        status = tray["status"]
        lines, colour = _label(status, tray)
        target = None if tray["wanted"] is None else place_centre[tray["wanted"]["place"]]
        if tray["centre"] is not None:
            centre = np.array(tray["centre"]) * scale
        elif target is not None:
            centre = target
        else:
            continue
        x, y = (round(v) for v in centre)
        if status == "in place":
            cv2.circle(image, (x, y), 40, colour, 6, cv2.LINE_AA)
        elif status == "missing":
            cv2.drawMarker(image, (x, y), colour, cv2.MARKER_TILTED_CROSS, 80, 6, cv2.LINE_AA)
            rings.append(((x, y), tray["tray_id"]))
        if status.startswith("wrong place") and target is not None:
            tx, ty = (round(v) for v in target)
            cv2.arrowedLine(image, (x, y), (tx, ty), (0, 0, 0), 14, cv2.LINE_AA, tipLength=0.08)
            cv2.arrowedLine(image, (x, y), (tx, ty), colour, 8, cv2.LINE_AA, tipLength=0.08)
            rings.append(((tx, ty), tray["tray_id"]))
        if status in ("turned", "wrong place, turned"):
            _turn_arrow(image, (x, y), 70, _TURN_COLOUR)
        # Below the tray, or above it when that would run off the bottom of the photo.
        below = y + 100 + 25 * (len(lines) - 1) < image.shape[0] - 6
        labels.append(((x, y + 100 if below else y - 60 - 25 * (len(lines) - 1)), lines, colour))
    for (x, y), _tray in rings:
        cv2.circle(image, (x, y), 26, (0, 0, 0), 10, cv2.LINE_AA)
        cv2.circle(image, (x, y), 26, _PLACE_COLOUR, 5, cv2.LINE_AA)
    with text_layer(image) as layer:
        for (x, y), lines, colour in labels:
            for i, line in enumerate(lines):
                half = text_width(line, 0.7) / 2 + 3
                lx = round(min(max(x, half), image.shape[1] - half))
                layer.text(line, (lx, y + 25 * i), 0.7, colour, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
        for (x, y), tray_id in rings:
            line = f"Tray {tray_id} goes here"
            half = text_width(line, 0.6) / 2 + 3
            lx = round(min(max(x, half), image.shape[1] - half))
            layer.text(line, (lx, max(y - 40, 24)), 0.6, _PLACE_COLOUR, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
    return array_to_jpeg(image)


# Bump the version whenever the renderer would draw the same inputs differently.
images.register(images.Recipe("randomize_check", 4, _render_check_overlay))
