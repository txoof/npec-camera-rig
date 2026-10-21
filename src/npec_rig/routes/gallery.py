"""Routes for the Gallery page: the photo list and reduced copies of each photo."""

import logging
import sqlite3

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from npec_rig import database, images, photo_tags, validation
from npec_rig.calibration_store import CalibrationNotFoundError, CalibrationUnreadableError, load_saved_calibration
from npec_rig.camera import array_to_jpeg
from npec_rig.captures import PHOTO_KEY, capture_hours, list_recent_captures, photo_file
from npec_rig.routes.shared import derived_response, templates
from npec_rig.text_render import text_layer, text_width
from npec_rig.tags import CALIBRATION_ID_RANGE, CORNER_ID_RANGE, TRAY_ID_RANGE, TagDetection
from npec_rig.tray_placement import TrayPlacement, place_trays

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/gallery")
def gallery_page(request: Request) -> Response:
    """Capture button + recent-captures gallery, split out of the main page (2026-09-25):
    unrelated to camera/calibration setup, and cluttered a page that's supposed to be a quick
    Setup flow."""
    return templates.TemplateResponse(request, "gallery.html")


@router.get("/api/captures")
def api_captures(
    limit: int = Query(12, ge=1, le=200), before: str | None = None, experiment: int | None = None
) -> list[dict]:
    """Most recent captures for the gallery, newest first. `before` (an entry's `key`) gives the
    next page back in time; `experiment` (an id) only that experiment's photos."""
    if before is not None and not PHOTO_KEY.match(before):
        raise HTTPException(422, f"not a photo key: {before!r} (expected YYYY-MM-DDTHHMMSS_ffffff)")
    try:
        return list_recent_captures(limit=limit, before=before, experiment_id=experiment)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/captures/hours")
def api_capture_hours(experiment: int | None = None) -> list[dict]:
    """Photos per UTC hour, newest first: the gallery's Go to date list, counted by local day.
    `experiment` (an id) counts only that experiment's photos."""
    try:
        return capture_hours(experiment_id=experiment)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


def _tag_role(tag_id: int) -> str:
    for role, ids in (("tray", TRAY_ID_RANGE), ("calibration", CALIBRATION_ID_RANGE), ("corner", CORNER_ID_RANGE)):
        if tag_id in ids:
            return role
    return "other"


def _tray_placements(path: str, tags: list[TagDetection]) -> dict[int, TrayPlacement] | None:
    """Each tray tag in photo `path` placed with the calibration the photo was taken under, by
    tray ID; None when the photo has no calibration, or its calibration or slot layout cannot be
    read."""
    try:
        record = database.captures_by_path([path]).get(path)
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not read the capture row of %s", path)
        return None
    if record is None or not record.get("calibration"):
        return None
    try:
        artifact = load_saved_calibration(record["calibration"])
        slots = validation.slot_layout(artifact)["slots"]
    except (CalibrationNotFoundError, CalibrationUnreadableError, validation.ValidationRefusedError,
            photo_tags.FrameMissingError):
        return None
    return {p.tray_id: p for p in place_trays(tags, artifact.scale_field, slots)}


def _placement_json(p: TrayPlacement | None) -> dict | None:
    if p is None:
        return None
    return {"slot": p.slot, "a1_corner": p.a1_corner, "status": p.status, "margin_mm": round(p.margin_mm, 1)}


@router.get("/api/captures/tags/{path:path}")
def api_photo_tags(path: str) -> list[dict]:
    """The tags in gallery photo `path`: each one's ID, role (tray, calibration, corner or other)
    and centre in full-size pixels. A tray tag also has its `placement` (slot, A1 corner, status)
    from the photo's calibration, or None when the photo has none. Nothing is stored about trays."""
    tags = photo_tags.photo_tags_for(path)
    placements = _tray_placements(path, tags) or {}
    out = []
    for d in tags:
        entry = {"id": d.tag_id, "role": _tag_role(d.tag_id), "centre_px": [round(d.centre[0]), round(d.centre[1])]}
        if entry["role"] == "tray":
            entry["placement"] = _placement_json(placements.get(d.tag_id))
        out.append(entry)
    return out


# Gallery image sizes, as widths in pixels: a thumbnail, and a copy for the chamber screen when a
# thumbnail is tapped (#56). Never the 64MP original.
_GALLERY_WIDTHS = {"thumb": 480, "screen": 1600}


@router.get("/gallery/image/tags/{path:path}")
def gallery_tags_image(path: str) -> Response:
    """Photo `path` at the screen copy's size with every tag outlined and labelled with its ID,
    tray tags as "Tray <id>", and each placed tray's outline, slot and A1 corner. Searches the photo first if it has not been searched yet. The tags
    are part of the image's inputs, so it is drawn again whenever the stored tags change."""
    found = photo_tags.photo_tags_for(path)
    tags = [{"id": d.tag_id, "corners": [list(c) for c in d.corners]} for d in found]
    trays = [
        {"id": p.tray_id, "outline": [list(c) for c in p.outline], "slot": p.slot, "a1_corner": p.a1_corner, "status": p.status}
        for p in (_tray_placements(path, found) or {}).values()
    ]
    inputs = {"photo": path, "width": _GALLERY_WIDTHS["screen"], "tags": tags, "trays": trays}
    return derived_response("gallery_tags", path, inputs)


@router.get("/gallery/image/{size}/{path:path}")
def gallery_image(size: str, path: str) -> Response:
    """Photo `path` (a gallery entry's `path`) reduced to `size`, made once and then served from
    the derived image store (images.py)."""
    if size not in _GALLERY_WIDTHS:
        raise HTTPException(404, f"no gallery size {size!r}")
    try:
        found = photo_file(path)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if found is None:
        raise HTTPException(404, f"photo {path} not found")
    return derived_response(f"gallery_{size}", path, {"photo": path, "width": _GALLERY_WIDTHS[size]})


def _render_gallery_image(inputs: dict) -> bytes:
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, _scale = images.reduced_frame(found, inputs["width"])
    return array_to_jpeg(image)


_TAG_COLOUR = (255, 0, 255)  # magenta, as tags.draw_overlay
_TRAY_COLOUR = (255, 220, 0)  # yellow, apart from the tags and the blue trays


def _render_gallery_tags_image(inputs: dict) -> bytes:
    """Outlines each tag on the reduced copy, a thick line for a tray tag and a thin one for the
    others, with its label beside it: the words, not the line, say which is a tray tag. Each placed
    tray gets its outline, and its slot and A1 corner written at its centre, with its status when
    it is not simply placed. Its tag marks the A1 corner."""
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, scale = images.reduced_frame(found, inputs["width"])
    tags = [(tag["id"], np.array(tag["corners"]) * scale) for tag in inputs["tags"]]
    trays = [(tray, np.array(tray["outline"]) * scale) for tray in inputs.get("trays", [])]
    for tray, outline in trays:
        cv2.polylines(image, [outline.round().astype(np.int32).reshape(-1, 1, 2)], isClosed=True, color=_TRAY_COLOUR, thickness=3)
    for tag_id, corners in tags:
        points = corners.round().astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(image, [points], isClosed=True, color=_TAG_COLOUR, thickness=3 if tag_id in TRAY_ID_RANGE else 1)
    with text_layer(image) as layer:
        for tag_id, corners in tags:
            label = f"Tray {tag_id}" if tag_id in TRAY_ID_RANGE else str(tag_id)
            top = corners[:, 1].min()
            half = text_width(label, 0.8) / 2 + 3  # kept inside the frame, a tag at the edge too
            x = min(max(corners[:, 0].mean(), half), image.shape[1] - half)
            layer.text(
                label,
                (round(x), max(round(top) - 6, 24)),
                0.8,
                _TAG_COLOUR,
                anchor="ms",
                stroke_width=3,
                stroke_fill=(0, 0, 0),
            )
        for tray, outline in trays:
            x, y = outline.mean(axis=0)
            lines = [f"{tray['slot']}, A1 {tray['a1_corner']}"] + ([tray["status"].upper()] if tray["status"] != "placed" else [])
            for i, line in enumerate(lines):
                layer.text(line, (round(x), round(y) + 28 * i), 0.8, _TRAY_COLOUR, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
    return array_to_jpeg(image)


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
images.register(images.Recipe("gallery_thumb", 1, _render_gallery_image))
images.register(images.Recipe("gallery_screen", 1, _render_gallery_image))
images.register(images.Recipe("gallery_tags", 2, _render_gallery_tags_image))
