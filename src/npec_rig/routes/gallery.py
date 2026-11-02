"""Routes for the Gallery page: the photo list and reduced copies of each photo."""

import logging
import sqlite3
from datetime import UTC, datetime

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from npec_rig import exclusions, images, photo_tags, tray_readings
from npec_rig.camera import array_to_jpeg
from npec_rig.captures import PHOTO_KEY, capture_hours, list_recent_captures, photo_file
from npec_rig.routes.shared import derived_response, templates
from npec_rig.segmentation import EXG_MIN, ExGSegmenter
from npec_rig.text_render import text_layer, text_width
from npec_rig.tags import CALIBRATION_ID_RANGE, CORNER_ID_RANGE, TRAY_ID_RANGE, TagDetection

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
    # Each photo's saved tray readings (#222) with its light mark and floors (#288), None until
    # it has been read. Like the records (captures._with_database_rows), a database that cannot
    # be read leaves the photos listed.
    try:
        for item in items:
            record = item.get("record")
            item["trays"] = tray_readings.capture_readings(record) if record else None
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


@router.get("/api/captures/light-warning")
def api_light_warning(experiment: int) -> dict | None:
    """The experiment's light warning (#288): the hours of light off its usual level and when,
    None when there is none or it was dismissed."""
    return exclusions.light_warning(experiment)


@router.post("/api/captures/light-warning/dismiss")
def api_dismiss_light_warning(experiment: int, until: str) -> dict | None:
    """Dismiss the experiment's light warning as shown, up to `until` (its `last`), saved with
    the time; returns the warning now."""
    try:
        exclusions.dismiss_light_warning(experiment, now=datetime.now(UTC).isoformat(), until=until)
    except ValueError as exc:
        raise HTTPException(422, f"not a time: {until!r}") from exc
    return exclusions.light_warning(experiment)


def _tag_role(tag_id: int) -> str:
    for role, ids in (("tray", TRAY_ID_RANGE), ("calibration", CALIBRATION_ID_RANGE), ("corner", CORNER_ID_RANGE)):
        if tag_id in ids:
            return role
    return "other"


def _saved_trays(path: str) -> list[dict]:
    """Photo `path`'s trays as its saved reading has them (#331): found in the photo and named by
    the tag inside each, or a tag seen with no tray found around it. The photo is read first when
    it has not been (Show tags is the ask for older photos, Aaron 2026-10-22); a reading with
    plant areas is kept as it is. Empty when it cannot be read: the trays are an extra."""
    try:
        reading = tray_readings.read_photo(path, unless_measured=True)
    except LookupError:
        return []  # no record in rig.db: nothing to read the photo with or save against
    except Exception:
        logger.exception("Could not read the trays of %s", path)
        try:
            reading = tray_readings.photo_readings(path)
        except LookupError:
            return []
    return reading["trays"] if reading else []


def _reading_trays(path: str) -> list[dict]:
    """Photo `path`'s trays as its saved reading has them, without reading the photo; empty when
    it has not been read."""
    try:
        reading = tray_readings.photo_readings(path)
    except LookupError:
        return []
    return reading["trays"] if reading else []


def _tray_of(tag: TagDetection, trays: list[dict]) -> dict | None:
    """The saved tray tag `tag` names: the outline its centre lies inside, or the tray seen at
    the tag itself when no outline holds it."""
    for tray in trays:
        if tray["tray_id"] != tag.tag_id:
            continue
        if tray["outline_px"]:
            contour = np.array(tray["outline_px"], np.float32).reshape(-1, 1, 2)
            if cv2.pointPolygonTest(contour, (float(tag.centre[0]), float(tag.centre[1])), False) >= 0:
                return tray
        elif np.hypot(tray["centre_px"][0] - tag.centre[0], tray["centre_px"][1] - tag.centre[1]) < 1:
            return tray
    return None


def _placement_json(tray: dict | None) -> dict | None:
    if tray is None:
        return None
    # No slot: trays can lie anywhere on the table (#331); Info names each tray's table location (#332).
    return {"found": tray["found"], "warnings": tray["warnings"]}


@router.get("/api/captures/tags/{path:path}")
def api_photo_tags(path: str) -> list[dict]:
    """The tags in gallery photo `path`: each one's ID, role (tray, calibration, corner or other)
    and centre in full-size pixels. A tray tag also has its `placement`: how its tray was found
    and its warnings (#331), from the photo's tray reading, which is saved first when the photo
    has not been read (#222); None when the photo cannot be read for trays."""
    tags = photo_tags.photo_tags_for(path)
    trays = _saved_trays(path)
    out = []
    for d in tags:
        entry = {"id": d.tag_id, "role": _tag_role(d.tag_id), "centre_px": [round(d.centre[0]), round(d.centre[1])]}
        if entry["role"] == "tray":
            entry["placement"] = _placement_json(_tray_of(d, trays))
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
    """Photo `path` at the screen copy's size with every tag outlined, each tag but a tray
    tag labelled with its ID, and each tray of the photo's reading (#331): its outline found in
    the photo, named by its tag or "No tag" and the table location it lies in (#332), with its
    warnings, or a cross where a tag was seen with no tray found around it. Searches the photo for
    tags first if not yet done, but draws only a tray reading already saved: the tag list
    (`api_photo_tags`) is what reads the photo, so one tap never reads the 64MP photo twice
    (review of #334). The tags and trays are part of the image's inputs, so it is drawn again
    whenever either changes."""
    _require_photo(path)  # 404 for a deleted photo, whose tags photo_tags still knows (#287)
    found = photo_tags.photo_tags_for(path)
    tags = [{"id": d.tag_id, "corners": [list(c) for c in d.corners]} for d in found]
    trays = [
        {"id": t["tray_id"], "outline": t["outline_px"], "centre": t["centre_px"], "found": t["found"], "warnings": t["warnings"],
         "location": t.get("location")}
        for t in _reading_trays(path)
    ]
    inputs = {"photo": path, "width": _GALLERY_WIDTHS["screen"], "tags": tags, "trays": trays}
    return derived_response("gallery_tags", path, inputs)


@router.get("/gallery/image/green/{path:path}")
def gallery_green_image(path: str) -> Response:
    """Photo `path` at the screen copy's size with the pixels the green threshold takes as plant
    tinted magenta (#74). The mask is made on the screen copy, for looking at, not for areas."""
    _require_photo(path)
    return derived_response("gallery_green", path, {"photo": path, "width": _GALLERY_WIDTHS["screen"], "exg_min": EXG_MIN})


@router.get("/gallery/image/{size}/{path:path}")
def gallery_image(size: str, path: str) -> Response:
    """Photo `path` (a gallery entry's `path`) reduced to `size`, made once and then served from
    the derived image store (images.py)."""
    if size not in _GALLERY_WIDTHS:
        raise HTTPException(404, f"no gallery size {size!r}")
    _require_photo(path)
    return derived_response(f"gallery_{size}", path, {"photo": path, "width": _GALLERY_WIDTHS[size]})


def _require_photo(path: str) -> None:
    """422 for a path that is not a photo path, 404 for a photo no longer on the rig."""
    try:
        found = photo_file(path)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if found is None:
        raise HTTPException(404, f"photo {path} not found")


def _render_gallery_image(inputs: dict) -> bytes:
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, _scale = images.reduced_frame(found, inputs["width"])
    return array_to_jpeg(image)


def _render_gallery_green_image(inputs: dict) -> bytes:
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, _scale = images.reduced_frame(found, inputs["width"])
    mask = ExGSegmenter(inputs["exg_min"]).segment(image)
    tinted = image.astype(np.float32)
    tinted[mask] = 0.4 * tinted[mask] + 0.6 * np.array(_PLANT_COLOUR, dtype=np.float32)
    return array_to_jpeg(tinted.round().astype(np.uint8))


_PLANT_COLOUR = (255, 0, 255)  # magenta: stands out from green leaves, brown soil and blue trays
_TAG_COLOUR = (255, 0, 255)  # magenta, as tags.draw_overlay
_TRAY_COLOUR = (255, 220, 0)  # yellow, apart from the tags and the blue trays


# Each warning in a few words on the image, where the trays sit close together; Info has them in
# full.
_SHORT_WARNINGS = {"partly outside the photo": "PARTLY OUTSIDE", "two tags in one tray outline": "TWO TAGS"}


def _tray_labels(inputs: dict) -> list[tuple[np.ndarray | None, np.ndarray, list[str], bool]]:
    """Each outline once, with its lines of words: two trays may share one (two tags in one tray
    outline), and an old reading has no outline or found. A tag seen with no tray found around it
    has no outline, only its centre, and is marked with a cross (the last item)."""
    groups: dict[tuple, dict] = {}
    for tray in inputs.get("trays", []):
        outline = tray.get("outline")
        key = tuple(map(tuple, outline)) if outline else ("seen", tray["id"], tuple(tray["centre"]))
        group = groups.setdefault(key, {"outline": outline, "centre": tray["centre"], "ids": [], "found": tray.get("found"), "warnings": [],
                                        "location": tray.get("location")})
        if tray["id"] is not None:
            group["ids"].append(tray["id"])
        group["warnings"] += [w for w in tray.get("warnings") or [] if w not in group["warnings"]]
    out = []
    for group in groups.values():
        ids = ", ".join(map(str, sorted(group["ids"])))
        if group["outline"] is None:
            if group["found"] == "tag only":
                lines = [f"Tag {ids},", "no tray found"]  # two short lines: the tags lie close together
                out.append((None, np.array(group["centre"], float), lines, True))
            else:
                # Read before #331 with no outline to give it (its calibration is gone): the name
                # alone at its centre, never a tag seen with no tray found (review of #334).
                out.append((None, np.array(group["centre"], float), [f"Tray {ids}"], False))
            continue
        name = f"Tray {ids}" if len(group["ids"]) == 1 else f"Trays {ids}" if group["ids"] else "No tag"
        if group["location"]:
            name += f", {group['location']}"  # the table location, not a slot (#332)
        lines = [name] + [_SHORT_WARNINGS.get(w, w.upper()) for w in group["warnings"] if w != "no tag"]
        outline = np.array(group["outline"], float)
        out.append((outline, outline.mean(axis=0), lines, False))
    return out


def _render_gallery_tags_image(inputs: dict) -> bytes:
    """Outlines each tag on the reduced copy, a thick line for a tray tag and a thin one for the
    others, each other tag with its ID beside it. Each tray found in the photo gets its outline,
    with "Tray <id>" or "No tag" and its warnings written at its centre; a tag seen with no tray
    found around it gets a cross and "Tag <id>, no tray found" (#331): a tray's number is written
    once, never on its tag as well."""
    found = photo_file(inputs["photo"])
    if found is None:
        raise HTTPException(404, f"photo {inputs['photo']} not found")
    image, scale = images.reduced_frame(found, inputs["width"])
    tags = [(tag["id"], np.array(tag["corners"]) * scale) for tag in inputs["tags"]]
    trays = [
        (None if outline is None else outline * scale, centre * scale, lines, cross)
        for outline, centre, lines, cross in _tray_labels(inputs)
    ]
    for outline, centre, _lines, cross in trays:
        if outline is not None:
            cv2.polylines(image, [outline.round().astype(np.int32).reshape(-1, 1, 2)], isClosed=True, color=_TRAY_COLOUR, thickness=3)
        elif cross:
            x, y = centre.round().astype(int)
            cv2.drawMarker(image, (int(x), int(y)), _TRAY_COLOUR, markerType=cv2.MARKER_TILTED_CROSS, markerSize=48, thickness=4)
    for tag_id, corners in tags:
        points = corners.round().astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(image, [points], isClosed=True, color=_TAG_COLOUR, thickness=3 if tag_id in TRAY_ID_RANGE else 1)
    with text_layer(image) as layer:
        for tag_id, corners in tags:
            # A tray tag's number is written once, on its tray's outline or by its cross (Aaron,
            # 2026-10-30): the tag keeps only its box.
            if tag_id in TRAY_ID_RANGE:
                continue
            label = str(tag_id)
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
        for outline, (x, y), lines, cross in trays:
            # A cross's words sit below it, clear of the tag's box; a tray's warnings are smaller
            # than its name.
            y0 = y + (52 if cross else 0)
            for i, line in enumerate(lines):
                size = 0.8 if i == 0 and outline is not None else 0.6
                half = text_width(line, size) / 2 + 3  # kept inside the frame, as the tag labels
                layer.text(line, (round(min(max(x, half), image.shape[1] - half)), round(y0) + 26 * i), size, _TRAY_COLOUR, anchor="ms", stroke_width=3, stroke_fill=(0, 0, 0))
    return array_to_jpeg(image)


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
images.register(images.Recipe("gallery_thumb", 1, _render_gallery_image))
images.register(images.Recipe("gallery_screen", 1, _render_gallery_image))
images.register(images.Recipe("gallery_tags", 5, _render_gallery_tags_image))
images.register(images.Recipe("gallery_green", 1, _render_gallery_green_image))
