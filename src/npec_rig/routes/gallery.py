"""Routes for the Gallery page: the photo list and reduced copies of each photo."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from npec_rig import images
from npec_rig.camera import array_to_jpeg
from npec_rig.captures import PHOTO_KEY, capture_hours, list_recent_captures, photo_file
from npec_rig.routes.shared import derived_response, templates

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


# Gallery image sizes, as widths in pixels: a thumbnail, and a copy for the chamber screen when a
# thumbnail is tapped (#56). Never the 64MP original.
_GALLERY_WIDTHS = {"thumb": 480, "screen": 1600}


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


# Bump a recipe's version whenever its renderer would draw the same inputs differently.
images.register(images.Recipe("gallery_thumb", 1, _render_gallery_image))
images.register(images.Recipe("gallery_screen", 1, _render_gallery_image))
