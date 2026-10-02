import asyncio
import itertools
import logging
import re
import time
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import numpy as np
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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
    CURRENT_FILENAME,
    calibration_root,
    list_calibrations,
    load_calibration,
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
from npec_rig.camera import (
    CameraBusyError,
    CameraManager,
    LensMovedDuringLockError,
    LensNotSettledError,
    array_to_jpeg,
)
from npec_rig.certainty_map import (
    MIN_MOVED_FRACTION,
    SlotLayoutError,
    SlotResult,
    build_slot_layout,
    calibration_centres,
    certainty_by_slot,
    group_sheets,
    moved_fraction,
    render_certainty_map,
    render_problem_frame,
    round_errors_by_slot,
    sheets_by_slot,
    slot_layout_from_dict,
    slot_layout_to_dict,
)
from npec_rig.captures import captures_root, list_recent_captures, save_capture
from npec_rig.settings import load_settings, save_setting
from npec_rig.tags import (
    ASSUMED_CALIBRATION_TAG_SIZE_MM,
    ASSUMED_CORNER_TAG_SIZE_MM,
    CALIBRATION_ID_RANGE,
    CORNER_ID_RANGE,
    detect_tags,
)
from npec_rig import images, validation_store
from npec_rig.tripwire import (
    build_corner_baseline,
    check_tripwire,
    corner_level_readings,
)

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
# The printable sheets themselves (reference/calibration-sheets/), not app code -- served so the
# Setup wizard can hand the operator a direct download link at the point they're needed.
CALIBRATION_SHEETS_DIR = Path(__file__).parent.parent.parent / "reference" / "calibration-sheets"
PREVIEW_BOUNDARY = b"frame"
PREVIEW_FPS_LIMIT = 10.0
ROI_STREAM_FPS_LIMIT = 5.0

captures_root().mkdir(parents=True, exist_ok=True)
calibration_root().mkdir(parents=True, exist_ok=True)

app = FastAPI(title="NPEC Camera Rig")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
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


@app.get("/setup")
def setup_page(request: Request) -> Response:
    """Setup menu: links to Focus & Square, Calibration, and Health check. One-and-done (or
    occasional) rig setup, kept separate from everyday capture/browsing."""
    return templates.TemplateResponse(request, "setup_index.html")


@app.get("/setup/focus")
def setup_focus_page(request: Request) -> Response:
    """Autofocus, manual lens position, and the squareness guide lines."""
    return templates.TemplateResponse(request, "setup_focus.html")


@app.get("/setup/calibration")
def setup_calibration_page(request: Request) -> Response:
    """The calibration wizard (7 steps) and its diagnostics."""
    return templates.TemplateResponse(request, "setup_calibration.html")


@app.get("/setup/calibration-history")
def setup_calibration_history_page(request: Request) -> Response:
    """Browse every saved calibration, promote one to active, or delete old ones -- split out of
    the wizard (2026-09-26): reachable on its own, not nested three `<details>` deep inside Step
    5, and usable without walking the linear wizard."""
    return templates.TemplateResponse(request, "setup_calibration_history.html")


@app.get("/setup/calibration-history/{stem}")
def setup_calibration_history_diagnostics_page(stem: str, request: Request) -> Response:
    """Diagnostics drill-down for one arbitrary saved calibration -- TODO.md's "let the two
    heatmaps and the best-vs-worst-tag rank plots be viewed for a past calibration, not just
    whatever's live." One template serves any `stem`; the page reads it from its own URL and
    looks itself up in `/calibration/list` client-side, same list the history page already
    fetches -- no new metadata endpoint needed.
    """
    return templates.TemplateResponse(request, "setup_calibration_history_diagnostics.html")


@app.get("/setup/validation")
def setup_validation_page(request: Request) -> Response:
    """Validate the active calibration: move the sheets and trays, capture a round, repeat. Runs
    on demand, independent of the calibration wizard."""
    return templates.TemplateResponse(request, "setup_validation.html")


@app.get("/setup/health-check")
def setup_health_check_page(request: Request) -> Response:
    """On-demand checks outside the linear calibration wizard -- currently just the tripwire
    check, moved here from the wizard (Aaron, 2026-09-25: "should not be part of the wizard,
    should be moved to a 'health check' screen")."""
    return templates.TemplateResponse(request, "setup_health_check.html")


@app.get("/gallery")
def gallery_page(request: Request) -> Response:
    """Capture button + recent-captures gallery, split out of the main page (2026-09-25):
    unrelated to camera/calibration setup, and cluttered a page that's supposed to be a quick
    Setup flow."""
    return templates.TemplateResponse(request, "gallery.html")


@app.get("/snapshot.jpg")
def snapshot() -> Response:
    """One JPEG from the main stream."""
    jpeg = CameraManager.instance().snapshot_jpeg()
    return Response(content=jpeg, media_type="image/jpeg")


_mjpeg_stream_ids = itertools.count(1)


async def _mjpeg_frames(
    request: Request, jpeg_source: Callable[[], bytes], fps_limit: float, name: str
) -> AsyncIterator[bytes]:
    """Yield `multipart/x-mixed-replace` chunks from `jpeg_source`, capped at `fps_limit`.

    An async generator, not a sync one: Starlette runs a sync generator's `next()` through
    anyio's threadpool with cancellation shielded for the duration of each call, so a client
    disconnect cannot stop it mid-call, only between calls -- and if `jpeg_source` blocks (its
    own lock contended), it never gets to "between calls" at all, pinning that worker thread
    forever. An async generator's own `await`s are ordinary cancellable ones; only the actual
    blocking camera call goes through the threadpool, and CameraManager bounds that wait
    (STREAM_LOCK_TIMEOUT) so it always returns control here. Checking `is_disconnected()`
    explicitly, rather than relying only on Starlette's own disconnect handling, means a closed
    tab stops this loop before the next frame grab even starts, not up to one frame later.
    Confirmed against the installed Starlette/anyio source, 2026-09-29 (see TODO.md).
    """
    stream_id = next(_mjpeg_stream_ids)
    min_interval = 1.0 / fps_limit
    frame_count = 0
    logger.info("mjpeg stream %s#%d: start", name, stream_id)
    try:
        while True:
            if await request.is_disconnected():
                break
            start = time.monotonic()
            try:
                jpeg = await run_in_threadpool(jpeg_source)
            except CameraBusyError:
                # Already spent up to STREAM_LOCK_TIMEOUT blocked in the failed acquire --
                # only sleep whatever's left of min_interval, not the whole thing again.
                elapsed = time.monotonic() - start
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
                continue
            yield (
                b"--" + PREVIEW_BOUNDARY + b"\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
            )
            frame_count += 1
            elapsed = time.monotonic() - start
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
    finally:
        logger.info("mjpeg stream %s#%d: end, %d frames", name, stream_id, frame_count)


def _mjpeg_response(
    request: Request, jpeg_source: Callable[[], bytes], fps_limit: float, name: str
) -> StreamingResponse:
    """Wrap `_mjpeg_frames` in the streaming response FastAPI needs to serve it."""
    return StreamingResponse(
        _mjpeg_frames(request, jpeg_source, fps_limit, name),
        media_type=f"multipart/x-mixed-replace; boundary={PREVIEW_BOUNDARY.decode()}",
    )


@app.get("/preview.mjpg")
def preview(request: Request) -> StreamingResponse:
    """Live MJPEG preview from the lores stream."""
    manager = CameraManager.instance()
    return _mjpeg_response(request, manager.preview_jpeg, PREVIEW_FPS_LIMIT, "preview")


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
def focus_roi_stream(request: Request) -> StreamingResponse:
    """Magnified 1:1 MJPEG stream of the focus ROI, for the focus aid."""
    manager = CameraManager.instance()
    return _mjpeg_response(request, manager.roi_crop_jpeg, ROI_STREAM_FPS_LIMIT, "focus_roi")


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
    """Drive the lens to the position last set, the one consistent way, and lock it there."""
    try:
        return CameraManager.instance().lock_focus()
    except (LensNotSettledError, LensMovedDuringLockError) as exc:
        raise HTTPException(409, f"{exc}: focus is not locked, press Lock focus again") from exc


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


def _resolve_table_dims(
    table_width_mm: float | None,
    table_length_mm: float | None,
    corner_tag_size_mm: float | None,
    *,
    persist: bool,
) -> tuple[float | None, float | None, float | None]:
    """Resolve the three table-position-view display values against what's already persisted
    (`settings.py`), used by both `run_calibration` and `save_table_dims` -- found duplicated
    (and already diverging) by code review 2026-09-26.

    A given value only counts as real if it's a positive number. 0 or negative can't be a
    physical tag size or table span; letting one through used to reach
    `_outer_edge_span_to_centre_distance_mm` as `corner_tag_size_mm=0`, which doesn't trip that
    function's own non-positive guard (0 subtracts nothing, rather than producing a non-positive
    result) -- silently rendering "to scale" with the tag-width correction missing entirely, and
    persisting the bad 0 as every future run's default. An invalid value here is treated exactly
    like a blank field: falls back to whatever was last validly persisted, and is never written.

    `persist=False` for a `promote=False` comparison run (PLAN.md's two-baseline/two-height
    tests): a deliberately different value for that one comparison run must not silently become
    every future real run's default, the way `promote=False` already keeps `current.json`
    untouched.
    """
    persisted = load_settings()
    resolved: list[float | None] = []
    for name, value in (
        ("table_width_mm", table_width_mm),
        ("table_length_mm", table_length_mm),
        ("corner_tag_size_mm", corner_tag_size_mm),
    ):
        if value is not None and value > 0:
            if persist:
                save_setting(name, value)
            resolved.append(value)
        else:
            resolved.append(persisted.get(name))
    return tuple(resolved)  # type: ignore[return-value]


# Calibration's own readiness gate (TODO.md, "Give Lock focus a real function"): all 4 mounted
# corner tags, not check_tripwire's 2-tag minimum -- that check answers "has something changed
# since a good baseline", this one answers "is the camera positioned well enough to calibrate at
# all", which is a stricter bar by design (Aaron, 2026-09-28).
CORNER_TAGS_REQUIRED_FOR_CALIBRATION = 4


def _calibration_readiness() -> dict:
    """Live check for calibration's own gate: is focus currently locked, and are all 4 corner
    tags currently detectable. Cheap -- a main-stream frame, not a full-res capture -- so it can
    be polled from the wizard, and re-checked by `/calibration/run` itself right before the
    expensive capture (the backend never trusts a frontend-only check).
    """
    manager = CameraManager.instance()
    focus_locked = manager.focus_status()["locked"]
    frame = manager.capture_array()
    corner_tags_detected = len([d for d in detect_tags(frame) if d.tag_id in CORNER_ID_RANGE])
    return {
        "focus_locked": focus_locked,
        "corner_tags_detected": corner_tags_detected,
        "corner_tags_required": CORNER_TAGS_REQUIRED_FOR_CALIBRATION,
        "ready": focus_locked and corner_tags_detected >= CORNER_TAGS_REQUIRED_FOR_CALIBRATION,
    }


@app.get("/calibration/readiness")
def calibration_readiness() -> dict:
    """`_calibration_readiness` as its own endpoint, for the wizard to poll live on Step 5."""
    return _calibration_readiness()


def _build_calibration_delta(
    previous: CalibrationArtifact | None,
    *,
    residual_std_pct: float,
    corner_tag_count: int,
    calibration_tag_size_mm: float,
    lens_position: float | None,
    px_per_mm_at_centre: float | None,
    frame_width: int,
    frame_height: int,
) -> dict | None:
    """Compare this run's headline numbers against whatever was the active calibration right
    before this run replaced it (Aaron, 2026-09-28). Cheap, no re-detection: every value here
    already lives on the saved artifact or was just computed for this run's own result -- the
    same caution TODO.md already applies to the history browser (re-detecting tags from every
    saved frame just to show a number is real cost, not a one-line change).
    """
    if previous is None:
        return None

    previous_corner_count = (
        len(previous.corner_baseline.corners_by_id) if previous.corner_baseline else 0
    )
    try:
        previous_px_per_mm = previous.scale_field.px_per_mm(frame_width / 2, frame_height / 2)
    except ValueError:
        previous_px_per_mm = None

    def metric(previous_value: float | None, current_value: float | None) -> dict:
        delta = (
            current_value - previous_value
            if previous_value is not None and current_value is not None
            else None
        )
        return {"previous": previous_value, "current": current_value, "delta": delta}

    return {
        "previous_created_at": previous.created_at,
        "residual_std_pct": metric(previous.scale_field.residual_std_pct, residual_std_pct),
        "corner_tags_detected": metric(previous_corner_count, corner_tag_count),
        "calibration_tag_size_mm": metric(
            previous.calibration_tag_size_mm, calibration_tag_size_mm
        ),
        "lens_position": metric(previous.lens_position, lens_position),
        "px_per_mm_at_centre": metric(previous_px_per_mm, px_per_mm_at_centre),
    }


@app.post("/calibration/run")
def run_calibration(
    promote: bool = True,
    calibration_tag_size_mm: float | None = None,
    table_width_mm: float | None = None,
    table_length_mm: float | None = None,
    corner_tag_size_mm: float | None = None,
    override_focus_gate: bool = False,
) -> dict:
    """Setup calibration (PLAN.md M2 section A): capture a full-res still, detect tags, build the
    scale field and install report, and save the frame plus the resulting artifact.

    `override_focus_gate=True` skips the readiness gate below (focus locked, all 4 corner tags
    detected) -- a data-quality check, not a safety one, so it warns rather than refuses outright:
    the operator always has an explicit way through (Aaron, 2026-09-28, see TODO.md's Lock-focus
    entry). Without it, a failed gate returns early with `gate_failed: true` and no capture, so a
    predictably-bad run doesn't cost the ~8.5s full-res round trip.

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
    `calibration_tag_size_mm`).

    All three go through `_resolve_table_dims` (see its docstring): remembered across runs via
    `settings.py`'s key/value store, not the `CalibrationArtifact`; only a real (positive),
    explicitly-given value is ever persisted, and only when `promote` is also true -- a
    `promote=False` comparison run's own values are used for *this* run's table view but never
    become the sticky default for every real run after it, the same way `promote=False` already
    keeps `current.json` untouched.
    """
    # Checked before anything below, including _resolve_table_dims' own persistence -- a
    # refused run (no capture, gate_failed) must have no lasting side effects. Found by
    # /code-review 2026-09-28: this used to run after _resolve_table_dims, so a gate-refused
    # run still silently overwrote the sticky table-dims defaults.
    if not override_focus_gate:
        readiness = _calibration_readiness()
        if not readiness["ready"]:
            if not readiness["focus_locked"]:
                message = "Focus is not confirmed -- confirm focus before running calibration."
            else:
                required = readiness["corner_tags_required"]
                message = (
                    f"{readiness['corner_tags_detected']} of {required} corner tags detected. "
                    f"A minimum of {required} is required for a successful calibration."
                )
            return {"error": message, "gate_failed": True, **readiness}

    tag_size_mm = calibration_tag_size_mm if calibration_tag_size_mm is not None else (
        ASSUMED_CALIBRATION_TAG_SIZE_MM
    )
    table_width_mm, table_length_mm, corner_tag_size_mm = _resolve_table_dims(
        table_width_mm, table_length_mm, corner_tag_size_mm, persist=promote
    )
    corner_size_mm = corner_tag_size_mm if corner_tag_size_mm is not None else (
        ASSUMED_CORNER_TAG_SIZE_MM
    )

    manager = CameraManager.instance()

    # Captured before this run's own save/promote below can overwrite current.json -- the
    # "previous" half of the post-run delta.
    previous_artifact = load_current_calibration()

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
    result["previous_calibration_comparison"] = _build_calibration_delta(
        previous_artifact,
        residual_std_pct=field.residual_std_pct,
        corner_tag_count=len(corner_baseline.corners_by_id) if corner_baseline else 0,
        calibration_tag_size_mm=tag_size_mm,
        lens_position=lens_position,
        px_per_mm_at_centre=result["px_per_mm_at_centre"],
        frame_width=frame_width,
        frame_height=frame_height,
    )
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

    Also carries the calibration-history browser's per-entry summary stats -- only ones already
    on the artifact (`residual_std_pct`, `calibration_tag_size_mm`, corner-tag count), no
    re-detection from the saved frame. Coplanarity/holdout/area-scale error need re-detecting
    tags from each saved frame and are deliberately left out of this list (reference/plans/
    calibration-history-browser.md's "real gaps" section) -- a per-entry drill-down view is where
    those belong, not a list that must stay fast with many saved runs.
    """
    current = load_current_calibration()
    entries = []
    for path in reversed(list_calibrations()):
        stem = path.stem
        try:
            artifact = load_calibration(path)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "saved calibration %s is unreadable, listing without stats: %s", path, exc
            )
            artifact = None
        stats = (
            {
                "created_at": artifact.created_at,
                "residual_std_pct": artifact.scale_field.residual_std_pct,
                "calibration_tag_size_mm": artifact.calibration_tag_size_mm,
                "corner_tag_count": (
                    len(artifact.corner_baseline.corners_by_id) if artifact.corner_baseline else 0
                ),
                "is_current": current is not None and artifact.created_at == current.created_at,
            }
            if artifact is not None
            else {
                "created_at": None,
                "residual_std_pct": None,
                "calibration_tag_size_mm": None,
                "corner_tag_count": None,
                "is_current": False,
            }
        )
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
                "stem": stem,
                "filename": path.name,
                "url": f"/calibration/files/{path.name}",
                "frame_url": frame_url,
                "heatmap_url": heatmap_url,
                "area_shape_heatmap_url": area_shape_heatmap_url,
                "accuracy_shape_heatmap_url": accuracy_shape_heatmap_url,
                "table_view_url": table_view_url,
                "table_view_shape_url": table_view_shape_url,
                **stats,
            }
        )
    return entries


def _saved_calibration_path(stem: str) -> Path:
    """Resolve a calibration-history `stem` (a URL path segment) to its artifact JSON file,
    refusing anything that isn't a plain filename component -- `stem` comes straight from the
    request path, and building a file path by string interpolation is exactly the shape that
    needs this before it ever gets used, not after.
    """
    root = calibration_root()
    path = (root / f"{stem}.json").resolve()
    if path.parent != root.resolve() or path.name in (".json", CURRENT_FILENAME):
        raise HTTPException(404, f"no saved calibration {stem!r}")
    if not path.exists():
        raise HTTPException(404, f"no saved calibration {stem!r}")
    return path


def _load_saved_artifact(stem: str) -> CalibrationArtifact:
    """Load a saved calibration by history `stem`, for routes that need the full artifact rather
    than just its list-view stats -- the diagnostics drill-down and promote both want this."""
    path = _saved_calibration_path(stem)
    try:
        return load_calibration(path)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"saved calibration {stem!r} could not be read: {exc}") from exc


@app.post("/calibration/{stem}/promote")
def promote_calibration(stem: str) -> dict:
    """Make a previously saved calibration the active one, no fresh capture -- the
    calibration-history browser's "reactivate an old, still-valid measurement" action
    (reference/plans/calibration-history-browser.md). Reuses `save_calibration`'s own
    promote-to-`current.json` mechanism, the same one a live run's "set as current baseline"
    checkbox already uses.
    """
    artifact = _load_saved_artifact(stem)
    save_calibration(artifact, stem=stem, promote=True)
    return {"promoted": stem, "created_at": artifact.created_at}


@app.delete("/calibration/{stem}")
def delete_calibration(stem: str) -> dict:
    """Delete a saved calibration's artifact JSON, frame, and heatmap files -- disk hygiene for
    old runs (reference/plans/calibration-history-browser.md). Refuses to delete whichever one
    `current.json` currently points at, which would otherwise leave the rig's active calibration
    with a snapshot/report that no longer exists.

    `current.json` has no record of which stem it was promoted from (compared by `created_at`
    instead, see `list_calibration_artifacts`), so confirming "not the active one" requires
    reading both files. If either can't be read, this refuses rather than guessing -- a corrupt
    `current.json` means we don't know what's active at all, and a corrupt target stem can't be
    ruled out as the active one either (it could have been promoted before whatever damaged it).
    """
    path = _saved_calibration_path(stem)

    current_path = calibration_root() / CURRENT_FILENAME
    current = load_current_calibration() if current_path.exists() else None
    if current_path.exists() and current is None:
        raise HTTPException(
            409,
            "the active calibration (current.json) could not be read -- refusing to delete "
            "anything until that is resolved, since which calibration is active cannot be "
            "confirmed",
        )

    try:
        artifact = load_calibration(path)
    except (ValueError, KeyError, TypeError) as exc:
        if current is not None:
            raise HTTPException(
                409,
                f"saved calibration {stem!r} could not be read ({exc}) -- refusing to delete it "
                "since whether it is the active calibration cannot be confirmed from its content",
            ) from exc
    else:
        if current is not None and artifact.created_at == current.created_at:
            raise HTTPException(409, "refusing to delete the active calibration")

    path.unlink()
    (calibration_root() / "frames" / f"{stem}.jpg").unlink(missing_ok=True)
    # A validation session only means anything against its own calibration.
    validation_store.delete_sessions_for_calibration(stem)
    validation_store.delete_slot_layout(stem)
    for suffix in (
        "",
        "_area-shape",
        "_accuracy-shape",
        "_table-view",
        "_table-view-area-shape",
    ):
        (calibration_root() / "heatmaps" / f"{stem}{suffix}.jpg").unlink(missing_ok=True)
    return {"deleted": stem}


@app.get("/calibration/current")
def current_calibration() -> dict:
    """Summary of the active saved calibration, so the operator knows which one is live.

    `table_width_mm`/`table_length_mm`/`corner_tag_size_mm` come from `settings.py`, not the
    artifact -- they're the operator's last real, explicitly-typed values (see `run_calibration`'s
    docstring), available for the UI to pre-fill from regardless of whether a calibration has
    ever been saved.
    """
    persisted = load_settings()
    table_dims = {
        "table_width_mm": persisted.get("table_width_mm"),
        "table_length_mm": persisted.get("table_length_mm"),
        "corner_tag_size_mm": persisted.get("corner_tag_size_mm"),
    }
    artifact = load_current_calibration()
    if artifact is None:
        return {"exists": False, **table_dims}
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
        "frame_stem": artifact.frame_stem,
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
        **table_dims,
    }


@app.post("/calibration/table-dims")
def save_table_dims(
    table_width_mm: float | None = None,
    table_length_mm: float | None = None,
    corner_tag_size_mm: float | None = None,
) -> dict:
    """Save table width/length/corner-tag size on their own, with no camera capture and no tag
    detection -- these are pure display-convenience values for the table-position view (see
    `run_calibration`'s docstring), not measurements a calibration produces. Before this endpoint
    existed, the only way to persist them was as a side effect of "Run calibration", which needs
    real calibration sheets in frame to succeed -- so once sheets come off the table after setup
    (Step 6), there was no way to fix a mistyped table dimension without redoing the whole
    physical setup (Aaron, 2026-09-25: "There's no way to enter the table width and length in mm.
    There's no submit button.").

    Uses `_resolve_table_dims` (see its docstring) -- only a given, positive value is written; a
    blank or non-positive field keeps whatever was persisted before.
    """
    table_width_mm, table_length_mm, corner_tag_size_mm = _resolve_table_dims(
        table_width_mm, table_length_mm, corner_tag_size_mm, persist=True
    )
    return {
        "table_width_mm": table_width_mm,
        "table_length_mm": table_length_mm,
        "corner_tag_size_mm": corner_tag_size_mm,
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
        # Drop the outgoing entry before decoding the new frame, not after -- the calibration-
        # history drill-down makes switching frame_stem (not just growing the same one) a normal
        # user action, so without this the previous ~180MB frame array stays referenced by this
        # global while the next one is decoded, holding two full-res frames live at once. Same
        # OOM condition this cache exists to prevent (see the comment above it), just at 2x
        # instead of 4x.
        _cached_frame_detections = None
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


def _rank_plot_response(artifact: CalibrationArtifact, metric: str) -> Response:
    """Sorted best-vs-worst-tag plot (TODO.md) for `artifact`'s own `metric` --
    `"scale_residual"` (the confidence heatmap's number) or `"shape_distortion"` (the area-shape
    heatmap's number). See `_metric_points` for why this re-detects tags each call.
    """
    signed_points, label, _frame = _metric_points(metric, artifact)

    if len(signed_points) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")

    points = [(abs(v), tag_id, x, y) for v, tag_id, x, y in signed_points]
    image = render_rank_plot(points, label=label)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/current/rank-plot")
def current_rank_plot(metric: str = "scale_residual") -> Response:
    """`_rank_plot_response` for the live calibration."""
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    return _rank_plot_response(artifact, metric)


@app.get("/calibration/{stem}/rank-plot")
def stem_rank_plot(stem: str, metric: str = "scale_residual") -> Response:
    """`_rank_plot_response` for an arbitrary saved calibration `stem` -- the calibration-history
    browser's per-entry diagnostics drill-down (TODO.md, reference/plans/
    calibration-history-browser.md), not just whatever's currently active."""
    return _rank_plot_response(_load_saved_artifact(stem), metric)


def _best_worst_photo_response(artifact: CalibrationArtifact, metric: str) -> Response:
    """`artifact`'s actual saved photo, with its best and worst tag for `metric` circled directly
    on it -- green for best, red for worst, each labelled with its magnitude -- so the worst tag
    can be found and inspected physically, not just read off the rank plot's abstract rank axis.
    See `_metric_points` for why this re-detects tags each call.
    """
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


@app.get("/calibration/current/best-worst-photo")
def current_best_worst_photo(metric: str = "scale_residual") -> Response:
    """`_best_worst_photo_response` for the live calibration."""
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    return _best_worst_photo_response(artifact, metric)


@app.get("/calibration/{stem}/best-worst-photo")
def stem_best_worst_photo(stem: str, metric: str = "scale_residual") -> Response:
    """`_best_worst_photo_response` for an arbitrary saved calibration `stem` -- see
    `stem_rank_plot`."""
    return _best_worst_photo_response(_load_saved_artifact(stem), metric)


def _radial_plot_response(artifact: CalibrationArtifact, metric: str) -> Response:
    """PLAN.md's own evidence-gate measurement (see `calibration_viz.render_radial_residual_plot`):
    signed `metric` residual against distance from the image centre, one point per tag, with a
    linear fit and its R^2 -- the specific measurement that decides whether a structured lens/
    parallax distortion signature is present, as opposed to the coverage-and-outlier-driven
    pattern the confidence heatmap otherwise shows. See `_metric_points` for why this re-detects
    tags each call.
    """
    signed_points, label, frame = _metric_points(metric, artifact)

    if len(signed_points) < 2:
        raise HTTPException(409, "not enough calibration tags detected in the saved frame to plot")

    cx, cy = frame.shape[1] / 2, frame.shape[0] / 2
    points = [(float(np.hypot(x - cx, y - cy)), value, tag_id) for value, tag_id, x, y in signed_points]

    image = render_radial_residual_plot(points, label=label)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/current/radial-plot")
def current_radial_plot(metric: str = "scale_residual") -> Response:
    """`_radial_plot_response` for the live calibration."""
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    return _radial_plot_response(artifact, metric)


@app.get("/calibration/{stem}/radial-plot")
def stem_radial_plot(stem: str, metric: str = "scale_residual") -> Response:
    """`_radial_plot_response` for an arbitrary saved calibration `stem` -- see
    `stem_rank_plot`."""
    return _radial_plot_response(_load_saved_artifact(stem), metric)


def _certainty_dome_plot_response(artifact: CalibrationArtifact) -> Response:
    """Aaron, 2026-09-25: an honest display of modeled area-measurement certainty as a function
    of distance from the image centre, where certainty *should* be highest -- claimed uncertainty
    (`UncertaintyField.local_uncertainty_pct`, already computed and persisted on every run, no new
    measurement) sampled at each detected calibration tag's position. See `_detect_tags_cached`
    for why this re-detects tags from the saved frame rather than the live camera.
    """
    if artifact.uncertainty_field is None:
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


@app.get("/calibration/current/certainty-dome-plot")
def current_certainty_dome_plot() -> Response:
    """`_certainty_dome_plot_response` for the live calibration."""
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with an uncertainty field saved yet")
    return _certainty_dome_plot_response(artifact)


@app.get("/calibration/{stem}/certainty-dome-plot")
def stem_certainty_dome_plot(stem: str) -> Response:
    """`_certainty_dome_plot_response` for an arbitrary saved calibration `stem` -- see
    `stem_rank_plot`."""
    return _certainty_dome_plot_response(_load_saved_artifact(stem))


# Validation captures for the certainty map. `_detect_tags_cached` keeps one full frame for the
# calibration diagnostics; a full 64MP frame is ~180MB, so holding several would be the OOM
# condition that cache exists to prevent. Captures never stay in memory at full size: their tags
# come from the analysis store (images.py) and the copy to draw on is decoded straight to
# _CAPTURE_PREVIEW_WIDTH. Full-size frames live at once, at most: the cached calibration frame, a
# second calibration frame while that cache switches stems (under _frame_detection_lock), and one
# capture being analysed for the first time (under images._full_decode, a separate lock).
_CAPTURE_REF = re.compile(r"^\d{4}-\d{2}-\d{2}/\d{6}_\d{6}$")
_CAPTURE_PREVIEW_WIDTH = 2000
_MAX_CAPTURES_PER_MAP = 12


def _capture_path(ref: str) -> Path:
    if not _CAPTURE_REF.match(ref):
        raise HTTPException(422, f"not a capture reference: {ref!r} (expected YYYY-MM-DD/HHMMSS_ffffff)")
    path = captures_root() / f"{ref}.jpg"
    if not path.exists():
        raise HTTPException(404, f"capture {ref} not found")
    return path


def _capture_tags(ref: str) -> list:
    """Capture `ref`'s tag detections, worked out once per photograph and then read from the
    analysis store (images.py), so even after a restart nothing decodes it at full size again.
    Stored tags are used even if the photograph itself has since been deleted."""
    if not _CAPTURE_REF.match(ref):
        raise HTTPException(422, f"not a capture reference: {ref!r} (expected YYYY-MM-DD/HHMMSS_ffffff)")
    stored = images.stored_tag_detections(ref)
    if stored is not None:
        return stored
    return images.tag_detections(ref, _capture_path(ref), detect=lambda frame: detect_tags(frame))


def _capture_preview(ref: str) -> tuple[np.ndarray, float]:
    """`(preview, preview_scale)`: capture `ref` decoded straight to about _CAPTURE_PREVIEW_WIDTH,
    with its scale relative to full-resolution pixel coordinates."""
    return images.reduced_frame(_capture_path(ref), _CAPTURE_PREVIEW_WIDTH)


def _certainty_map_response(artifact: CalibrationArtifact, captures: list[str]) -> Response:
    """Per-tray-slot area certainty (certainty_map.py) for `artifact`, pooled over validation
    `captures` taken after the sheets and trays were moved. Slots come from the calibration's own
    saved frame; the map is drawn on the last capture."""
    if not captures:
        raise HTTPException(
            422, "pass at least one validation capture: captures=YYYY-MM-DD/HHMMSS_ffffff"
        )
    if len(captures) > _MAX_CAPTURES_PER_MAP:
        raise HTTPException(422, f"at most {_MAX_CAPTURES_PER_MAP} validation captures per map")
    if artifact.frame_stem is None:
        raise HTTPException(409, "this calibration has no saved frame to take tray slots from")
    _frame, calibration_detections = _detect_tags_cached(artifact.frame_stem)
    per_capture = [_capture_tags(ref) for ref in captures]  # only the last is drawn on
    try:
        layout, results = certainty_by_slot(
            calibration_detections,
            per_capture,
            artifact.scale_field,
            artifact.calibration_tag_size_mm,
        )
    except SlotLayoutError as exc:
        raise HTTPException(409, str(exc)) from exc
    preview, scale = _capture_preview(captures[-1])
    caption = (
        f"Calibration {artifact.frame_stem}, {len(captures)} validation capture(s) pooled. "
        "95% of tags within the stated band, at tray-top height."
    )
    image = render_certainty_map(preview, layout, results, caption, frame_scale=scale)
    return Response(content=array_to_jpeg(image), media_type="image/jpeg")


@app.get("/calibration/current/certainty-map")
def current_certainty_map(captures: list[str] = Query(default=[])) -> Response:
    """`_certainty_map_response` for the live calibration."""
    artifact = load_current_calibration()
    if artifact is None:
        raise HTTPException(409, "no calibration with a saved frame yet")
    return _certainty_map_response(artifact, captures)


@app.get("/calibration/{stem}/certainty-map")
def stem_certainty_map(stem: str, captures: list[str] = Query(default=[])) -> Response:
    """`_certainty_map_response` for an arbitrary saved calibration `stem`."""
    return _certainty_map_response(_load_saved_artifact(stem), captures)


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


# --- Validation sessions ---
# One round at a time across the whole app: a round is a full-res capture plus a detection pass,
# and a double-clicked Capture button must not append two rounds from one layout.
_validation_lock = Lock()
# Focus-lock position must match the calibration's to this many dioptres (the lens reports
# positions to 0.01; a real refocus moves it by far more).
_LENS_POSITION_TOLERANCE = 0.005


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
        and abs(locked_at - artifact.lens_position) > _LENS_POSITION_TOLERANCE
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
    }


@app.get("/validation/sessions")
def list_validation_sessions() -> list[dict]:
    """Every validation session, newest first."""
    current_stem = _current_calibration_stem()
    return [_session_summary(s, current_stem) for s in validation_store.list_sessions()]


@app.post("/validation/sessions")
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
    _frame, detections = _detect_tags_cached(artifact.frame_stem)
    try:
        layout = build_slot_layout(
            group_sheets(detections, artifact.scale_field, artifact.calibration_tag_size_mm)
        )
    except SlotLayoutError as exc:
        raise HTTPException(409, f"this calibration cannot be validated: {exc}") from exc
    slots, centres = slot_layout_to_dict(layout), calibration_centres(detections)
    validation_store.save_slot_layout(artifact.frame_stem, slots, centres)
    return {"slots": slots, "calibration_centres": [list(c) for c in centres]}


@app.get("/validation/status")
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


@app.get("/validation/sessions/{session_id}")
def get_validation_session(session_id: str) -> dict:
    return _session_summary(_session_or_404(session_id), _current_calibration_stem())


@app.delete("/validation/sessions/{session_id}")
def delete_validation_session(session_id: str) -> dict:
    """Remove one session from history. Its captures stay in the gallery."""
    with _validation_lock:
        try:
            validation_store.delete_session(session_id)
        except validation_store.SessionNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
    images.forget_source(f"validation:{session_id}")
    return {"deleted": session_id}


@app.post("/validation/sessions/{session_id}/rounds")
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

        manager = CameraManager.instance()
        focus = manager.focus_status()
        try:
            array, sensor_metadata = manager.capture_full_res()
        except CameraBusyError as exc:
            raise HTTPException(409, f"camera busy: {exc}") from exc
        record = save_capture(
            array,
            {
                "lens_position": manager.get_lens_position(),
                "roi": manager.get_roi(),
                "focus": focus,
                "sensor_metadata": sensor_metadata,
                "validation_session": session_id,
            },
        )
        del array
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


@app.post("/validation/sessions/{session_id}/rounds/{index}/count")
def count_validation_round(session_id: str, index: int) -> dict:
    """Count a round the checks held back, on the operator's say-so (gates need an override).
    Only for reasons the map can still handle: focus and movement, never slot placement."""
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


@app.post("/validation/sessions/{session_id}/end")
def end_validation_session(session_id: str) -> dict:
    """End a validation: it keeps its rounds and results but takes no more. A validation with
    fewer than the required rounds stays provisional."""
    with _validation_lock:
        session = _session_or_404(session_id)
        validation_store.end_session(session)
        validation_store.save_session(session)
        return _session_summary(session, _current_calibration_stem())


@app.get("/validation/sessions/{session_id}/map")
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
    return _derived_response("validation_map", f"validation:{session_id}", inputs)


def _render_validation_map(inputs: dict) -> bytes:
    preview, scale = images.reduced_frame(_capture_path(inputs["capture"]), inputs["preview_width"])
    results = [
        SlotResult(r["name"], r["n"], r["p95_abs_pct"], r["median_pct"]) for r in inputs["results"]
    ]
    image = render_certainty_map(
        preview, slot_layout_from_dict(inputs["slots"]), results, inputs["caption"], frame_scale=scale
    )
    return array_to_jpeg(image)


def _derived_response(recipe: str, source: str, inputs: dict) -> Response:
    """A derived image from the store. `no-cache`: the browser asks again every time (the URL
    stays the same while the session changes), and the store answers from disk."""
    content, media_type = images.get(recipe, source, inputs)
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "no-cache"})


def _size_text(offset_pct: float) -> str:
    return f"{abs(offset_pct):.1f}% {'small' if offset_pct < 0 else 'large'}"


@app.get("/validation/sessions/{session_id}/rounds/{number}/problems")
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


@app.get("/validation/sessions/{session_id}/offsets")
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
    return _derived_response("problem_frame", f"validation:{session['id']}", inputs)


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
