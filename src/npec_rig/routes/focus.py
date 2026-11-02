"""Routes for the camera: the Focus page, live streams, camera controls, focus lock, camera health
and reset, and taking a photo."""

import asyncio
import itertools
import logging
import time
from collections.abc import AsyncIterator, Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from npec_rig import health
from npec_rig.camera import (
    CameraBusyError,
    CameraFaultError,
    CameraManager,
    FocusLockedError,
    LensMovedDuringLockError,
    LensNotSettledError,
)
from npec_rig.captures import take_photo
from npec_rig.routes.shared import templates

logger = logging.getLogger(__name__)

router = APIRouter()


PREVIEW_BOUNDARY = b"frame"
PREVIEW_FPS_LIMIT = 10.0
ROI_STREAM_FPS_LIMIT = 5.0
# How often a live stream asks again for a frame while the camera restarts.
CAMERA_FAULT_STREAM_RETRY_S = 1.0


@router.get("/setup/focus")
def setup_focus_page(request: Request) -> Response:
    """Autofocus, manual lens position, and the squareness guide lines."""
    return templates.TemplateResponse(request, "setup_focus.html")


@router.get("/snapshot.jpg")
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
            except CameraFaultError:
                # The camera is restarting (camera_process.py): keep the stream open and pick up
                # frames again once it is back, rather than ending the preview.
                await asyncio.sleep(CAMERA_FAULT_STREAM_RETRY_S)
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


@router.get("/preview.mjpg")
def preview(request: Request) -> StreamingResponse:
    """Live MJPEG preview from the lores stream."""
    manager = CameraManager.instance()
    return _mjpeg_response(request, manager.preview_jpeg, PREVIEW_FPS_LIMIT, "preview")


class LensPosition(BaseModel):
    """Manual lens position, in dioptres."""

    value: float


@router.get("/controls/lens-position")
def get_lens_position() -> LensPosition:
    """Current lens position."""
    return LensPosition(value=CameraManager.instance().get_lens_position())


@router.post("/controls/lens-position")
def set_lens_position(position: LensPosition) -> LensPosition:
    """Set lens position, rejecting values outside the probed range."""
    manager = CameraManager.instance()
    # Bounds come from the probed range, not a hardcoded constant — LensPosition's own max
    # has already been observed to change between probes (15.0, then 32.0).
    min_value, max_value, _ = manager.available_controls()["LensPosition"]
    if not min_value <= position.value <= max_value:
        raise HTTPException(422, f"value must be between {min_value} and {max_value}")
    try:
        manager.set_lens_position(position.value)
    except FocusLockedError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LensNotSettledError as exc:
        raise HTTPException(503, str(exc)) from exc
    return position


class ControlUpdate(BaseModel):
    """New value for a named generic control (see `/controls/{name}`)."""

    value: bool | float


@router.get("/controls")
def list_controls() -> dict:
    """Probed control ranges and their current values."""
    manager = CameraManager.instance()
    return {"available": manager.available_controls(), "values": manager.get_controls()}


@router.post("/controls/{name}")
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


@router.post("/focus/autofocus")
def autofocus() -> dict:
    """Run one hardware autofocus cycle, then return to manual. Refused while focus is locked."""
    try:
        return CameraManager.instance().autofocus()
    except FocusLockedError as exc:
        raise HTTPException(409, str(exc)) from exc


class RoiUpdate(BaseModel):
    """New focus ROI: top-left corner and optional square size."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    size: int | None = Field(default=None, gt=0)


@router.get("/focus/roi")
def get_roi() -> dict:
    """Current focus ROI."""
    return CameraManager.instance().get_roi()


@router.post("/focus/roi")
def set_roi(roi: RoiUpdate) -> dict:
    """Move the focus ROI."""
    return CameraManager.instance().set_roi(roi.x, roi.y, roi.size)


@router.get("/focus/score")
def focus_score() -> dict:
    """Laplacian-variance sharpness score of the current ROI."""
    return {"score": CameraManager.instance().focus_score()}


@router.get("/focus/roi.mjpg")
def focus_roi_stream(request: Request) -> StreamingResponse:
    """Magnified 1:1 MJPEG stream of the focus ROI, for the focus aid."""
    manager = CameraManager.instance()
    return _mjpeg_response(request, manager.roi_crop_jpeg, ROI_STREAM_FPS_LIMIT, "focus_roi")


@router.get("/focus/status")
def focus_status() -> dict:
    """Whether focus is locked, and the lens position it was locked at."""
    return CameraManager.instance().focus_status()


class PeakingSetting(BaseModel):
    """Whether the focus-peaking overlay is on."""

    enabled: bool


@router.get("/focus/peaking")
def get_peaking() -> dict:
    """Current focus-peaking setting."""
    return CameraManager.instance().get_peaking()


@router.post("/focus/peaking")
def set_peaking(setting: PeakingSetting) -> dict:
    """Turn the focus-peaking overlay on or off."""
    return CameraManager.instance().set_peaking(setting.enabled)


@router.post("/focus/lock")
def lock_focus() -> dict:
    """Drive the lens to the position last set, the one consistent way, and lock it there."""
    try:
        return CameraManager.instance().lock_focus()
    except LensNotSettledError as exc:
        raise HTTPException(503, f"{exc}; focus is not locked") from exc
    except LensMovedDuringLockError as exc:
        raise HTTPException(409, f"{exc}: focus is not locked, press Lock focus again") from exc


@router.get("/camera/health")
def camera_health() -> dict:
    """The camera's state for the status line on every page (health.py). The fleet endpoint
    (#82) will report the same. Only reads: the app start opens the camera (#252)."""
    return health.camera_health()


@router.post("/camera/reset")
def reset_camera() -> dict:
    """The Reset camera button: close and reopen the camera, which restarts the lens control, then
    drive the lens back to the locked (or last set) position and confirm it."""
    try:
        return CameraManager.instance().reset_camera()
    except LensNotSettledError as exc:
        raise HTTPException(
            503,
            f"The camera reset did not help, the lens still does not follow: restart the app "
            f"(set to {exc.target:.2f}, the camera reports {exc.reported:.2f})",
        ) from exc
    except LensMovedDuringLockError as exc:
        raise HTTPException(409, f"{exc}: press Reset camera again") from exc


@router.post("/focus/unlock")
def unlock_focus() -> dict:
    """Clear the locked lens position."""
    return CameraManager.instance().unlock_focus()


@router.post("/capture")
def capture() -> dict:
    """Full-res JPEG to disk plus its JSON sidecar (captures.take_photo)."""
    _array, record = take_photo("capture")
    return record
