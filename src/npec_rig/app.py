import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from npec_rig.calibration import (
    CalibrationArtifact,
    area_scale_samples,
    build_area_scale_field,
    build_calibration_report,
    build_scale_field,
    build_table_frame,
    build_uncertainty_field,
    scale_residual_samples,
)
from npec_rig.calibration_store import (
    calibration_root,
    list_calibrations,
    load_calibration_frame,
    load_current_calibration,
    save_calibration,
    save_calibration_accuracy_shape_heatmap,
    save_calibration_area_shape_heatmap,
    save_calibration_frame,
    save_calibration_heatmap,
    save_calibration_table_view,
    save_calibration_table_view_area_shape,
)
from npec_rig.calibration_viz import (
    ACCURACY_SHAPE_HEATMAP_K,
    AREA_SHAPE_HEATMAP_MAX_PCT,
    AREA_SHAPE_HEATMAP_MIN_PCT,
    HEATMAP_MAX_PCT,
    HEATMAP_MIN_PCT,
    render_area_shape_heatmap,
    render_best_worst_overlay,
    render_certainty_dome_plot,
    render_honesty_plot,
    render_level_overlay,
    render_radial_residual_plot,
    render_rank_plot,
    render_table_view,
    render_uncertainty_heatmap,
)
from npec_rig.camera import CameraManager, array_to_jpeg
from npec_rig.captures import captures_root, list_recent_captures, save_capture
from npec_rig.tags import (
    ASSUMED_CALIBRATION_TAG_SIZE_MM,
    ASSUMED_CORNER_TAG_SIZE_MM,
    CALIBRATION_ID_RANGE,
    CORNER_ID_RANGE,
    detect_tags,
)
from npec_rig.tripwire import (
    build_corner_baseline,
    check_tripwire,
    corner_level_readings,
)

STATIC_DIR = Path(__file__).parent / "static"
# The printable sheets themselves (reference/calibration-sheets/), not app code -- served so the
# Setup wizard can hand the operator a direct download link at the point they're needed.
CALIBRATION_SHEETS_DIR = Path(__file__).parent.parent.parent / "reference" / "calibration-sheets"
PREVIEW_BOUNDARY = b"frame"
PREVIEW_FPS_LIMIT = 10.0
ROI_STREAM_FPS_LIMIT = 5.0

captures_root().mkdir(parents=True, exist_ok=True)
calibration_root().mkdir(parents=True, exist_ok=True)

app = FastAPI(title="NPEC Camera Rig")
app.mount("/captures", StaticFiles(directory=str(captures_root())), name="captures")
# PLAN.md M2 section A: calibration is "frozen, versioned, exportable" -- this is the export.
# Serves both the timestamped artifact JSON and, under frames/, the full-res still each one
# came from (calibration_store.save_calibration_frame).
app.mount("/calibration/files", StaticFiles(directory=str(calibration_root())), name="calibration_files")
# Shared CSS (and any future shared JS) for the plain multi-page static frontend -- no build step,
# no templating, just files served as-is alongside the page routes below.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount(
    "/reference/calibration-sheets",
    StaticFiles(directory=str(CALIBRATION_SHEETS_DIR)),
    name="calibration_sheets",
)


@app.get("/")
def index() -> RedirectResponse:
    """Root redirects to the everyday page -- Setup is occasional, not the default landing spot
    (2026-09-25 Setup-pages redesign)."""
    return RedirectResponse(url="/gallery")


@app.get("/setup", response_class=HTMLResponse)
def setup_page() -> str:
    """Setup menu: links to Focus & Square and Calibration. One-and-done (or occasional) rig
    setup, kept separate from everyday capture/browsing."""
    return (STATIC_DIR / "setup_index.html").read_text()


@app.get("/setup/focus", response_class=HTMLResponse)
def setup_focus_page() -> str:
    """Autofocus, manual lens position, and the squareness guide lines."""
    return (STATIC_DIR / "setup_focus.html").read_text()


@app.get("/setup/calibration", response_class=HTMLResponse)
def setup_calibration_page() -> str:
    """The calibration wizard (7 steps) and its diagnostics."""
    return (STATIC_DIR / "setup_calibration.html").read_text()


@app.get("/gallery", response_class=HTMLResponse)
def gallery_page() -> str:
    """Capture button + recent-captures gallery, split out of the main page (2026-09-25):
    unrelated to camera/calibration setup, and cluttered a page that's supposed to be a quick
    Setup flow."""
    return (STATIC_DIR / "gallery.html").read_text()


@app.get("/snapshot.jpg")
def snapshot() -> Response:
    """One JPEG from the main stream."""
    jpeg = CameraManager.instance().snapshot_jpeg()
    return Response(content=jpeg, media_type="image/jpeg")


def _mjpeg_frames(jpeg_source: Callable[[], bytes], fps_limit: float) -> Iterator[bytes]:
    """Yield `multipart/x-mixed-replace` chunks from `jpeg_source`, capped at `fps_limit`."""
    min_interval = 1.0 / fps_limit
    while True:
        start = time.monotonic()
        jpeg = jpeg_source()
        yield (
            b"--" + PREVIEW_BOUNDARY + b"\r\n"
            b"Content-Type: image/jpeg\r\n"
            b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
        )
        elapsed = time.monotonic() - start
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)


def _mjpeg_response(jpeg_source: Callable[[], bytes], fps_limit: float) -> StreamingResponse:
    """Wrap `_mjpeg_frames` in the streaming response FastAPI needs to serve it."""
    return StreamingResponse(
        _mjpeg_frames(jpeg_source, fps_limit),
        media_type=f"multipart/x-mixed-replace; boundary={PREVIEW_BOUNDARY.decode()}",
    )


@app.get("/preview.mjpg")
def preview() -> StreamingResponse:
    """Live MJPEG preview from the lores stream."""
    manager = CameraManager.instance()
    return _mjpeg_response(manager.preview_jpeg, PREVIEW_FPS_LIMIT)


class LensPosition(BaseModel):
    """Manual lens position, in dioptres."""

    value: float


@app.get("/controls/lens-position")
def get_lens_position() -> LensPosition:
    """Current lens position."""
    return LensPosition(value=CameraManager.instance().get_lens_position())


@app.post("/controls/lens-position")
def set_lens_position(position: LensPosition) -> LensPosition:
    """Set lens position, rejecting values outside the probed range."""
    manager = CameraManager.instance()
    # Bounds come from the probed range, not a hardcoded constant — LensPosition's own max
    # has already been observed to change between probes (15.0, then 32.0).
    min_value, max_value, _ = manager.available_controls()["LensPosition"]
    if not min_value <= position.value <= max_value:
        raise HTTPException(422, f"value must be between {min_value} and {max_value}")
    manager.set_lens_position(position.value)
    return position


class ControlUpdate(BaseModel):
    """New value for a named generic control (see `/controls/{name}`)."""

    value: bool | float


@app.get("/controls")
def list_controls() -> dict:
    """Probed control ranges and their current values."""
    manager = CameraManager.instance()
    return {"available": manager.available_controls(), "values": manager.get_controls()}


@app.post("/controls/{name}")
def set_control(name: str, update: ControlUpdate) -> dict:
    """Set one probed control by name, rejecting unknown names and out-of-range values."""
    manager = CameraManager.instance()
    available = manager.available_controls()
    # LensPosition has its own dedicated endpoint above (coarse/fine UI, autofocus) — not
    # reachable through this generic one.
    if name == "LensPosition" or name not in available:
        raise HTTPException(404, f"Unknown control: {name}")
    min_value, max_value, _ = available[name]
    value: bool | int | float
    if isinstance(min_value, bool):
        value = bool(update.value)
    elif isinstance(min_value, int):
        value = int(update.value)
    else:
        value = float(update.value)
    if not isinstance(value, bool) and not (min_value <= value <= max_value):
        raise HTTPException(422, f"value must be between {min_value} and {max_value}")
    return manager.set_control(name, value)


@app.post("/focus/autofocus")
def autofocus() -> dict:
    """Run one hardware autofocus cycle, then return to manual."""
    return CameraManager.instance().autofocus()


class RoiUpdate(BaseModel):
    """New focus ROI: top-left corner and optional square size."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    size: int | None = Field(default=None, gt=0)


@app.get("/focus/roi")
def get_roi() -> dict:
    """Current focus ROI."""
    return CameraManager.instance().get_roi()


@app.post("/focus/roi")
def set_roi(roi: RoiUpdate) -> dict:
    """Move the focus ROI."""
    return CameraManager.instance().set_roi(roi.x, roi.y, roi.size)


@app.get("/focus/score")
def focus_score() -> dict:
    """Laplacian-variance sharpness score of the current ROI."""
    return {"score": CameraManager.instance().focus_score()}


@app.get("/focus/roi.mjpg")
def focus_roi_stream() -> StreamingResponse:
    """Magnified 1:1 MJPEG stream of the focus ROI, for the focus aid."""
    manager = CameraManager.instance()
    return _mjpeg_response(manager.roi_crop_jpeg, ROI_STREAM_FPS_LIMIT)


@app.get("/focus/status")
def focus_status() -> dict:
    """Whether focus is locked, and the lens position it was locked at."""
    return CameraManager.instance().focus_status()


class PeakingSetting(BaseModel):
    """Whether the focus-peaking overlay is on."""

    enabled: bool


@app.get("/focus/peaking")
def get_peaking() -> dict:
    """Current focus-peaking setting."""
    return CameraManager.instance().get_peaking()


@app.post("/focus/peaking")
def set_peaking(setting: PeakingSetting) -> dict:
    """Turn the focus-peaking overlay on or off."""
    return CameraManager.instance().set_peaking(setting.enabled)


@app.post("/focus/lock")
def lock_focus() -> dict:
    """Record the current lens position as locked."""
    return CameraManager.instance().lock_focus()


@app.post("/focus/unlock")
def unlock_focus() -> dict:
    """Clear the locked lens position."""
    return CameraManager.instance().unlock_focus()


@app.post("/capture")
def capture() -> dict:
    """Full-res JPEG to disk plus a JSON sidecar of the current control values."""
    manager = CameraManager.instance()
    array, sensor_metadata = manager.capture_full_res()
    return save_capture(
        array,
        {
            "lens_position": manager.get_lens_position(),
            "roi": manager.get_roi(),
            "focus": manager.focus_status(),
            "sensor_metadata": sensor_metadata,
        },
    )


@app.get("/api/captures")
def api_captures(limit: int = 12) -> list[dict]:
    """Most recent captures for the gallery, newest first."""
    return list_recent_captures(limit=limit)


def _outer_edge_span_to_centre_distance_mm(
    outer_edge_span_mm: float | None, corner_tag_size_mm: float
) -> float | None:
    """Convert an operator's outer-edge-to-outer-edge tape measurement between two corner tags
    into the tag-centre-to-centre distance `render_table_view` actually needs.

    There's no mark at a tag's centre to measure to directly, so the operator lays a tape measure
    from one tag's outer edge (the corner facing away from the table) straight across to the
    opposite tag's outer edge and reads the number off -- no arithmetic on their end. Each outer
    edge sits half a tag width beyond its own tag's centre, so across both ends that's one full
    tag width to remove here, not on the tape measure. This assumes the tags are mounted
    axis-aligned with the table (true on this rig -- confirmed against a real saved frame, see
    TODO.md); a tag mounted at a real angle to the width/length axis would sit more than half its
    width beyond centre along that axis, and this would under-subtract.

    Returns `None` (falls back to a NOT-TO-SCALE canvas) rather than a non-positive number if
    `corner_tag_size_mm` comes out implausibly close to or bigger than what was measured -- almost
    certainly a data-entry mistake (e.g. an inner-edge measurement typed in instead), and a wrong
    aspect ratio is worse than none.
    """
    if outer_edge_span_mm is None:
        return None
    centre_to_centre_mm = outer_edge_span_mm - corner_tag_size_mm
    return centre_to_centre_mm if centre_to_centre_mm > 0 else None


@app.post("/calibration/run")
def run_calibration(
    promote: bool = True,
    calibration_tag_size_mm: float | None = None,
    table_width_mm: float | None = None,
    table_length_mm: float | None = None,
    corner_tag_size_mm: float | None = None,
) -> dict:
    """Setup calibration (PLAN.md M2 section A): capture a full-res still, detect tags, build the
    scale field and install report, and save the frame plus the resulting artifact.

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

    `table_width_mm`/`table_length_mm`, if given, are the operator's **outer-edge-to-outer-edge**
    tape measurement between corner tags (there's no mark at a tag's centre to measure to) --
    converted to the centre-to-centre distance `render_table_view` needs via
    `_outer_edge_span_to_centre_distance_mm`, using `corner_tag_size_mm` (calliper-measured if
    given, else `ASSUMED_CORNER_TAG_SIZE_MM`'s nominal placeholder, same pattern as
    `calibration_tag_size_mm`). None of the three is persisted anywhere (no `CalibrationArtifact`
    schema change): all are echoed straight back in the result so the UI can state which mode a
    given run's table view used, and there's nothing to pre-fill a repeat run from other than what
    the operator types again.
    """
    tag_size_mm = calibration_tag_size_mm if calibration_tag_size_mm is not None else (
        ASSUMED_CALIBRATION_TAG_SIZE_MM
    )
    corner_size_mm = corner_tag_size_mm if corner_tag_size_mm is not None else (
        ASSUMED_CORNER_TAG_SIZE_MM
    )

    manager = CameraManager.instance()
    array, _sensor_metadata = manager.capture_full_res()
    frame_height, frame_width = array.shape[0], array.shape[1]

    detections = detect_tags(array)
    calibration_detections = [d for d in detections if d.tag_id in CALIBRATION_ID_RANGE]
    corner_detections = [d for d in detections if d.tag_id in CORNER_ID_RANGE]
    tag_sizes_mm = {d.tag_id: tag_size_mm for d in calibration_detections}

    stem = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    frame_path = save_calibration_frame(array, stem=stem)

    result: dict = {
        "calibration_tags_detected": len(calibration_detections),
        "corner_tags_detected": len(corner_detections),
        "calibration_tag_size_mm": tag_size_mm,
        "calibration_tag_size_mm_is_default": calibration_tag_size_mm is None,
        "frame_path": str(frame_path),
        "table_width_mm": table_width_mm,
        "table_length_mm": table_length_mm,
        "corner_tag_size_mm": corner_size_mm,
        "corner_tag_size_mm_is_default": corner_tag_size_mm is None,
    }

    try:
        field = build_scale_field(detections, tag_sizes_mm)
    except ValueError as exc:
        result["error"] = str(exc)
        return result

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

    try:
        uncertainty_field = build_uncertainty_field(field, detections, tag_sizes_mm)
    except ValueError:
        uncertainty_field = None
    if uncertainty_field is not None:
        heatmap = render_uncertainty_heatmap(uncertainty_field, array)
        save_calibration_heatmap(heatmap, stem=stem)
        result["heatmap_url"] = f"/calibration/files/heatmaps/{stem}.jpg"

        # Same real per-tag residuals as the heatmap above, averaged over a much wider
        # neighbourhood (see ACCURACY_SHAPE_HEATMAP_K's own comment) -- for judging the rig's
        # overall accuracy shape once basic setup is done, not for finding exactly where
        # coverage is thin (that's the small-k heatmap's job). Aaron/supervisor, 2026-09-25.
        accuracy_shape_heatmap = render_uncertainty_heatmap(
            uncertainty_field, array, k=ACCURACY_SHAPE_HEATMAP_K
        )
        save_calibration_accuracy_shape_heatmap(accuracy_shape_heatmap, stem=stem)
        result["accuracy_shape_heatmap_url"] = f"/calibration/files/heatmaps/{stem}_accuracy-shape.jpg"
    else:
        result["heatmap_url"] = None
        result["accuracy_shape_heatmap_url"] = None

    try:
        area_field = build_area_scale_field(area_scale_samples(field, detections, tag_sizes_mm))
    except ValueError:
        area_field = None
    if area_field is not None:
        area_shape_heatmap = render_area_shape_heatmap(area_field, array)
        save_calibration_area_shape_heatmap(area_shape_heatmap, stem=stem)
        result["area_shape_heatmap_url"] = f"/calibration/files/heatmaps/{stem}_area-shape.jpg"
    else:
        result["area_shape_heatmap_url"] = None

    # The table-position trust view (PLAN.md 339-340's promised-but-unbuilt homography, see
    # calibration.TableFrame): same two fields as the two heatmaps above, painted instead on a
    # straightened top-down view anchored to the four corner tags, so "this spot" means the same
    # real position across different calibration runs. `covered_positions` reuses the calibration
    # tags' own positions already extracted above -- no new detection pass.
    try:
        table_frame = build_table_frame(corner_baseline) if corner_baseline is not None else None
    except ValueError:
        table_frame = None
    covered_positions = [d.centre for d in calibration_detections]
    render_width_mm = _outer_edge_span_to_centre_distance_mm(table_width_mm, corner_size_mm)
    render_length_mm = _outer_edge_span_to_centre_distance_mm(table_length_mm, corner_size_mm)
    # Distinct from "nothing entered": if width/length *were* entered but the conversion rejected
    # them (too small relative to corner_size_mm -- almost certainly a data-entry mistake), the
    # rendered view still falls back to NOT-TO-SCALE, but the result must say so plainly rather
    # than letting the UI echo the entered numbers next to a canvas that silently ignored them.
    result["table_view_to_scale"] = render_width_mm is not None and render_length_mm is not None

    if table_frame is not None and uncertainty_field is not None:
        table_view = render_table_view(
            array,
            table_frame,
            uncertainty_field.local_uncertainty_pct,
            covered_positions,
            label="scale residual",
            vmin=HEATMAP_MIN_PCT,
            vmax=HEATMAP_MAX_PCT,
            table_width_mm=render_width_mm,
            table_length_mm=render_length_mm,
        )
        save_calibration_table_view(table_view, stem=stem)
        result["table_view_url"] = f"/calibration/files/heatmaps/{stem}_table-view.jpg"
    else:
        result["table_view_url"] = None

    if table_frame is not None and area_field is not None:
        table_view_shape = render_table_view(
            array,
            table_frame,
            area_field.local_shape_factor_pct,
            covered_positions,
            label="area-shape distortion",
            vmin=AREA_SHAPE_HEATMAP_MIN_PCT,
            vmax=AREA_SHAPE_HEATMAP_MAX_PCT,
            table_width_mm=render_width_mm,
            table_length_mm=render_length_mm,
        )
        save_calibration_table_view_area_shape(table_view_shape, stem=stem)
        result["table_view_shape_url"] = (
            f"/calibration/files/heatmaps/{stem}_table-view-area-shape.jpg"
        )
    else:
        result["table_view_shape_url"] = None

    result["frame_url"] = f"/calibration/files/frames/{stem}.jpg"

    lens_position = manager.get_lens_position()
    artifact = CalibrationArtifact(
        created_at=datetime.now(timezone.utc).isoformat(),
        scale_field=field,
        corner_baseline=corner_baseline,
        lens_position=lens_position,
        calibration_tag_size_mm=tag_size_mm,
        uncertainty_field=uncertainty_field,
        frame_stem=stem,
    )
    result["artifact_path"] = str(save_calibration(artifact, stem=stem, promote=promote))
    result["promoted_to_current"] = promote
    result["lens_position"] = lens_position
    return result


@app.get("/calibration/list")
def list_calibration_artifacts() -> list[dict]:
    """Every saved calibration artifact, newest first, with URLs to download it and (if saved)
    the frame it came from -- the "exportable" half of PLAN.md's "frozen, versioned, exportable."
    """
    entries = []
    for path in reversed(list_calibrations()):
        frame_url = None
        if (calibration_root() / "frames" / f"{path.stem}.jpg").exists():
            frame_url = f"/calibration/files/frames/{path.stem}.jpg"
        heatmap_url = None
        if (calibration_root() / "heatmaps" / f"{path.stem}.jpg").exists():
            heatmap_url = f"/calibration/files/heatmaps/{path.stem}.jpg"
        area_shape_heatmap_url = None
        if (calibration_root() / "heatmaps" / f"{path.stem}_area-shape.jpg").exists():
            area_shape_heatmap_url = f"/calibration/files/heatmaps/{path.stem}_area-shape.jpg"
        accuracy_shape_heatmap_url = None
        if (calibration_root() / "heatmaps" / f"{path.stem}_accuracy-shape.jpg").exists():
            accuracy_shape_heatmap_url = f"/calibration/files/heatmaps/{path.stem}_accuracy-shape.jpg"
        table_view_url = None
        if (calibration_root() / "heatmaps" / f"{path.stem}_table-view.jpg").exists():
            table_view_url = f"/calibration/files/heatmaps/{path.stem}_table-view.jpg"
        table_view_shape_url = None
        if (calibration_root() / "heatmaps" / f"{path.stem}_table-view-area-shape.jpg").exists():
            table_view_shape_url = (
                f"/calibration/files/heatmaps/{path.stem}_table-view-area-shape.jpg"
            )
        entries.append(
            {
                "filename": path.name,
                "url": f"/calibration/files/{path.name}",
                "frame_url": frame_url,
                "heatmap_url": heatmap_url,
                "area_shape_heatmap_url": area_shape_heatmap_url,
                "accuracy_shape_heatmap_url": accuracy_shape_heatmap_url,
                "table_view_url": table_view_url,
                "table_view_shape_url": table_view_shape_url,
            }
        )
    return entries


@app.get("/calibration/current")
def current_calibration() -> dict:
    """Summary of the active saved calibration, so the operator knows which one is live."""
    artifact = load_current_calibration()
    if artifact is None:
        return {"exists": False}
    frame_url = f"/calibration/files/frames/{artifact.frame_stem}.jpg" if artifact.frame_stem else None
    heatmap_url = (
        f"/calibration/files/heatmaps/{artifact.frame_stem}.jpg"
        if artifact.frame_stem
        and (calibration_root() / "heatmaps" / f"{artifact.frame_stem}.jpg").exists()
        else None
    )
    area_shape_heatmap_url = (
        f"/calibration/files/heatmaps/{artifact.frame_stem}_area-shape.jpg"
        if artifact.frame_stem
        and (calibration_root() / "heatmaps" / f"{artifact.frame_stem}_area-shape.jpg").exists()
        else None
    )
    accuracy_shape_heatmap_url = (
        f"/calibration/files/heatmaps/{artifact.frame_stem}_accuracy-shape.jpg"
        if artifact.frame_stem
        and (calibration_root() / "heatmaps" / f"{artifact.frame_stem}_accuracy-shape.jpg").exists()
        else None
    )
    table_view_url = (
        f"/calibration/files/heatmaps/{artifact.frame_stem}_table-view.jpg"
        if artifact.frame_stem
        and (calibration_root() / "heatmaps" / f"{artifact.frame_stem}_table-view.jpg").exists()
        else None
    )
    table_view_shape_url = (
        f"/calibration/files/heatmaps/{artifact.frame_stem}_table-view-area-shape.jpg"
        if artifact.frame_stem
        and (
            calibration_root() / "heatmaps" / f"{artifact.frame_stem}_table-view-area-shape.jpg"
        ).exists()
        else None
    )
    return {
        "exists": True,
        "created_at": artifact.created_at,
        "residual_std_pct": artifact.scale_field.residual_std_pct,
        "lens_position": artifact.lens_position,
        "calibration_tag_size_mm": artifact.calibration_tag_size_mm,
        "corner_baseline_tags": (
            sorted(artifact.corner_baseline.corners_by_id) if artifact.corner_baseline else []
        ),
        "frame_url": frame_url,
        "heatmap_url": heatmap_url,
        "area_shape_heatmap_url": area_shape_heatmap_url,
        "accuracy_shape_heatmap_url": accuracy_shape_heatmap_url,
        "table_view_url": table_view_url,
        "table_view_shape_url": table_view_shape_url,
        "has_uncertainty_field": artifact.uncertainty_field is not None,
    }


@app.get("/calibration/current/uncertainty")
def current_uncertainty(x: float, y: float) -> dict:
    """Claimed uncertainty (%) at image position `(x, y)`, from the live calibration's own
    `UncertaintyField` -- the "claimed" half of PLAN.md's honesty plot. Aaron reads this off for
    wherever he's placed a known target, then measures the *actual* error with a ruler; the two
    together are one point on the plot.
    """
    artifact = load_current_calibration()
    if artifact is None or artifact.uncertainty_field is None:
        raise HTTPException(409, "no calibration with an uncertainty field saved yet")
    return {"uncertainty_pct": artifact.uncertainty_field.local_uncertainty_pct(x, y)}


class HonestyPlotPoint(BaseModel):
    """One physical target position for the honesty plot: where it is in the frame, and how far
    off the app's reading was there, measured with a ruler."""

    x: float
    y: float
    actual_error_pct: float


@app.post("/calibration/honesty-plot")
def honesty_plot(points: list[HonestyPlotPoint]) -> Response:
    """Render PLAN.md's M2 honesty plot from `points`: for each, look up the live calibration's
    claimed uncertainty at that position and pair it with the actual error Aaron measured there.

    Returns the rendered JPEG directly -- this is a one-off diagnostic chart for the chamber
    acceptance test, not a persisted artifact.
    """
    if not points:
        raise HTTPException(422, "need at least one point")
    artifact = load_current_calibration()
    if artifact is None or artifact.uncertainty_field is None:
        raise HTTPException(409, "no calibration with an uncertainty field saved yet")
    pairs = [
        (artifact.uncertainty_field.local_uncertainty_pct(p.x, p.y), p.actual_error_pct)
        for p in points
    ]
    image = render_honesty_plot(pairs)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


# The rank plot and best/worst photo endpoints each re-detect tags on the *full* saved frame
# (9152x6944 -- there's no persisted per-tag data to read instead, see `_metric_points`), and the
# UI fires all 4 of them (2 metrics x 2 views) right after every calibration run. Four concurrent
# full-resolution detection passes in one process is exactly what pushed the picamera2 worker to
# 6.6GB RSS and got it OOM-killed (dmesg-confirmed, 2026-09-22, right after this feature shipped)
# -- detect_tags's multi-window adaptive threshold sweep (tags.py's own DetectorParameters) isn't
# cheap at 64MP, and doing it four times at once is four times the transient memory, not four
# times the work. A one-entry cache, guarded by a lock so concurrent requests for the same frame
# queue instead of racing, turns that into one real decode-plus-detection pass plus three cache
# hits -- the cache holds the decoded frame itself (not just its detections), so a cache hit skips
# the ~180MB JPEG decode too, not only the detection sweep; otherwise all 4 requests would decode
# their own copy of the frame in parallel before any of them reached the lock, which is the same
# OOM condition under another name.
_frame_detection_lock = Lock()
_cached_frame_detections: tuple[str, np.ndarray, list] | None = None


def _detect_tags_cached(frame_stem: str) -> tuple[np.ndarray, list]:
    """Returns the *shared* cached frame array -- callers must not mutate it in place (draw on a
    copy instead), since every concurrent caller for the same frame_stem gets the same object."""
    global _cached_frame_detections
    with _frame_detection_lock:
        if _cached_frame_detections is not None and _cached_frame_detections[0] == frame_stem:
            return _cached_frame_detections[1], _cached_frame_detections[2]
        try:
            frame = load_calibration_frame(frame_stem)
        except FileNotFoundError:
            raise HTTPException(409, "the saved frame for this calibration is missing on disk")
        detections = detect_tags(frame)
        _cached_frame_detections = (frame_stem, frame, detections)
        return frame, detections


def _metric_points(metric: str, artifact: CalibrationArtifact) -> tuple[list[tuple[float, int, float, float]], str, np.ndarray]:
    """`(points, label, frame)` for `metric` against the live calibration -- shared by the rank
    plot and the best/worst photo overlay, so both read the same re-detection of the same saved
    frame rather than two separate (and possibly inconsistent) passes.

    `points` is `(signed_pct, tag_id, x, y)` per detected calibration tag -- signed, not
    magnitude, so a caller that needs a distortion signature's shape (the radial plot) doesn't
    have to reconstruct sign from an already-folded value; a caller that only wants magnitude
    (the rank plot, the best/worst photo) takes `abs()` itself at the point of use. Neither
    `scale_residual` nor `shape_distortion` is persisted per-tag in the artifact (only
    smoothed/aggregated forms are), so this always re-detects tags from the saved frame -- via
    `_detect_tags_cached`, not directly, see its own comment for why.
    """
    if metric not in ("scale_residual", "shape_distortion"):
        raise HTTPException(422, f"unknown metric {metric!r}, expected scale_residual or shape_distortion")
    if artifact.frame_stem is None:
        raise HTTPException(409, "no calibration with a saved frame yet")

    frame, detections = _detect_tags_cached(artifact.frame_stem)
    cal_detections = [d for d in detections if d.tag_id in CALIBRATION_ID_RANGE]
    tag_sizes_mm = {d.tag_id: artifact.calibration_tag_size_mm for d in cal_detections}

    if metric == "scale_residual":
        samples = scale_residual_samples(artifact.scale_field, cal_detections, tag_sizes_mm)
        points = [(s.residual_pct, s.tag_id, s.x, s.y) for s in samples]
        label = "scale residual"
    else:
        samples = area_scale_samples(artifact.scale_field, cal_detections, tag_sizes_mm)
        points = [(s.shape_factor_pct, s.tag_id, s.x, s.y) for s in samples]
        label = "area-shape distortion"

    return points, label, frame


@app.get("/calibration/current/rank-plot")
def current_rank_plot(metric: str = "scale_residual") -> Response:
    """Sorted best-vs-worst-tag plot (TODO.md) for the live calibration's own `metric` --
    `"scale_residual"` (the confidence heatmap's number) or `"shape_distortion"` (the area-shape
    heatmap's number). See `_metric_points` for why this re-detects tags each call.
    """
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    signed_points, label, _frame = _metric_points(metric, artifact)

    if len(signed_points) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")

    points = [(abs(v), tag_id, x, y) for v, tag_id, x, y in signed_points]
    image = render_rank_plot(points, label=label)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/current/best-worst-photo")
def current_best_worst_photo(metric: str = "scale_residual") -> Response:
    """The live calibration's actual saved photo, with its best and worst tag for `metric`
    circled directly on it -- green for best, red for worst, each labelled with its magnitude --
    so the worst tag can be found and inspected physically, not just read off the rank plot's
    abstract rank axis. See `_metric_points` for why this re-detects tags each call.
    """
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    signed_points, label, frame = _metric_points(metric, artifact)

    if len(signed_points) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")

    points = [(abs(v), tag_id, x, y) for v, tag_id, x, y in signed_points]
    ordered = sorted(points, key=lambda p: p[0])
    best_value, best_tag_id, best_x, best_y = ordered[0]
    worst_value, worst_tag_id, worst_x, worst_y = ordered[-1]

    image = render_best_worst_overlay(
        frame,
        best=(best_tag_id, best_x, best_y, best_value),
        worst=(worst_tag_id, worst_x, worst_y, worst_value),
        label=label,
    )
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/current/radial-plot")
def current_radial_plot(metric: str = "scale_residual") -> Response:
    """PLAN.md's own evidence-gate measurement (see `calibration_viz.render_radial_residual_plot`):
    signed `metric` residual against distance from the image centre, one point per tag, with a
    linear fit and its R^2 -- the specific measurement that decides whether a structured lens/
    parallax distortion signature is present, as opposed to the coverage-and-outlier-driven
    pattern the confidence heatmap otherwise shows. See `_metric_points` for why this re-detects
    tags each call.
    """
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    signed_points, label, frame = _metric_points(metric, artifact)

    if len(signed_points) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")

    cx, cy = frame.shape[1] / 2, frame.shape[0] / 2
    points = [(float(np.hypot(x - cx, y - cy)), value, tag_id) for value, tag_id, x, y in signed_points]

    image = render_radial_residual_plot(points, label=label)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/current/certainty-dome-plot")
def current_certainty_dome_plot() -> Response:
    """Aaron, 2026-09-25: an honest display of modeled area-measurement certainty as a function
    of distance from the image centre, where certainty *should* be highest -- claimed uncertainty
    (`UncertaintyField.local_uncertainty_pct`, already computed and persisted on every run, no new
    measurement) sampled at each detected calibration tag's position. See `_detect_tags_cached`
    for why this re-detects tags from the saved frame rather than the live camera.
    """
    artifact = load_current_calibration()
    if artifact is None or artifact.uncertainty_field is None:
        raise HTTPException(409, "no calibration with an uncertainty field saved yet")
    if artifact.frame_stem is None:
        raise HTTPException(409, "no calibration with a saved frame yet")

    frame, detections = _detect_tags_cached(artifact.frame_stem)
    cal_detections = [d for d in detections if d.tag_id in CALIBRATION_ID_RANGE]
    if len(cal_detections) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")

    cx, cy = frame.shape[1] / 2, frame.shape[0] / 2
    points = [
        (
            float(np.hypot(d.centre[0] - cx, d.centre[1] - cy)),
            artifact.uncertainty_field.local_uncertainty_pct(d.centre[0], d.centre[1]),
            d.tag_id,
        )
        for d in cal_detections
    ]

    image = render_certainty_dome_plot(points)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/orientation/level.jpg")
def live_level_overlay() -> Response:
    """Live co-planarity check for an installer levelling the rig by hand -- colored markers on
    the real camera image, not a rotation-in-degrees number (TODO.md: `roll_deg` "isn't super
    useful for an installer standing on a ladder"). No zero/baseline step needed:
    `corner_level_readings` (tripwire.py) compares the currently-detected corner tags to each
    other, which is valid regardless of how each one happens to be mounted -- see that function's
    docstring for the physical argument. Polled every 500ms while Step 2 of the wizard is showing.
    """
    manager = CameraManager.instance()
    frame = manager.capture_array()
    readings = corner_level_readings(detect_tags(frame))
    image = render_level_overlay(frame, readings)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.post("/calibration/tripwire/check")
def tripwire_check() -> dict:
    """Manual per-capture health check against the saved baseline (PLAN.md M2 section B).

    A "check now" button, not an automatic hook on every capture -- that needs a recurring
    capture loop, which doesn't exist until M3's scheduler. Built now anyway: without it, the M2
    roll/knock acceptance test has no way to trigger a tripwire check at all.
    """
    artifact = load_current_calibration()
    if artifact is None or artifact.corner_baseline is None:
        raise HTTPException(409, "no calibration baseline saved yet -- run a calibration first")

    manager = CameraManager.instance()
    array, _sensor_metadata = manager.capture_full_res()
    detections = detect_tags(array)
    result = check_tripwire(artifact.corner_baseline, detections)
    return {
        "verdict": result.verdict,
        "messages": list(result.messages),
        "roll_deg": result.roll_deg,
        "scale_delta_pct": result.scale_delta_pct,
    }
