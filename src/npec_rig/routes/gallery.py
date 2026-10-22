"""Routes for the Gallery page: the photo list and reduced copies of each photo."""

import logging
import sqlite3

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from npec_rig import database, images, photo_tags, tray_readings
from npec_rig.camera import array_to_jpeg
from npec_rig.captures import PHOTO_KEY, capture_hours, list_recent_captures, photo_file
from npec_rig.routes.shared import derived_response, templates
from npec_rig.text_render import text_layer, text_width
from npec_rig.tags import CALIBRATION_ID_RANGE, CORNER_ID_RANGE, TRAY_ID_RANGE, TagDetection
from npec_rig.tray_placement import TrayPlacement

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
        items = list_recent_captures(limit=limit, before=before, experiment_id=experiment)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    # Each photo's saved tray readings (#222), None until it has been read. Like the records
    # (captures._with_database_rows), a database that cannot be read leaves the photos listed.
    try:
        for item in items:
            record = item.get("record")
            item["trays"] = database.tray_readings(record["id"]) if record else None
    except (sqlite3.Error, RuntimeError):
        logger.exception("Could not read the tray readings for the gallery")
        for item in items:
            item["trays"] = None
    return items


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


def _tray_placements(path: str, tags: list[TagDetection]) -> dict[int, TrayPlacement]:
    """Each tray tag in photo `path` placed with its calibration, by tray ID; empty when the
    photo has no calibration with a usable slot layout. Placement is an extra on the tag list."""
    _status, placed = tray_readings.placements(path, tags)
    return {p.tray_id: p for p in placed}


def _placement_json(p: TrayPlacement | None) -> dict | None:
    if p is None:
        return None
    return {"slot": p.slot, "a1_corner": p.a1_corner, "status": p.status, "margin_mm": round(p.margin_mm, 1)}


@router.get("/api/captures/tags/{path:path}")
def api_photo_tags(path: str) -> list[dict]:
    """The tags in gallery photo `path`: each one's ID, role (tray, calibration, corner or other)
    and centre in full-size pixels. A tray tag also has its `placement` (slot, A1 corner, status)
    from the photo's calibration, or None when the photo has none. The photo's tray reading is
    saved as well (#222): older photos are read on demand."""
    tags = photo_tags.photo_tags_for(path)
    placements = _tray_placements(path, tags)
    # Older photos are read for their trays only when asked (Aaron, 2026-10-22): this is the ask.
    try:
        tray_readings.read_photo(path)
    except LookupError:
        pass  # no record in rig.db: nothing to save the reading against
    except Exception:
        # Saving the reading is an extra: the tags found are still returned.
        logger.exception("Could not save the tray reading of %s", path)
    out = []
    for d in tags:
        entry = {"id": d.tag_id, "role": _tag_role(d.tag_id), "centre_px": [round(d.centre[0]), round(d.centre[1])]}
        if entry["role"] == "tray":
            entry["placement"] = _placement_json(placements.get(d.tag_id))
        out.append(entry)
    return out


@router.get("/api/captures/trays/{path:path}")
def api_photo_trays(path: str) -> dict | None:
    """Gallery photo `path`'s saved tray reading (`database.tray_readings`); None when it has not
    been read or has no record in rig.db."""
    try:
        return tray_readings.photo_readings(path)
    except LookupError:
        return None


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
        for p in _tray_placements(path, found).values()
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
                half = text_width(line, 0.8) / 2 + 3  # kept inside the frame, as the tag labels
                layer.text(line, (round(min(max(x, half), image.shape[1] - half)), round(y) + 28 * i), 0.8, _TRAY_COLOUR, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
    return array_to_jpeg(image)


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
images.register(images.Recipe("gallery_thumb", 1, _render_gallery_image))
images.register(images.Recipe("gallery_screen", 1, _render_gallery_image))
images.register(images.Recipe("gallery_tags", 2, _render_gallery_tags_image))
