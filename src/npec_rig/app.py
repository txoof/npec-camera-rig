import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    CalibrationUnreadableError,
    calibration_root,
)
from npec_rig.camera import CameraFaultError, CameraManager
from npec_rig.captures import experiments_root, photos_root, record_app_start, record_app_stop
from npec_rig import database, images
from npec_rig.photo_tags import CaptureNotFoundError, CaptureRefError, FrameMissingError
from npec_rig.validation import RoundNotFoundError, ValidationRefusedError
from npec_rig.scheduler import Scheduler
from npec_rig.tray_readings import TrayReader
from npec_rig.validation_store import SessionNotFoundError
from npec_rig.routes import calibration, experiments, focus, gallery, shell, validation

STATIC_DIR = Path(__file__).parent / "static"
# The printable sheets themselves (reference/calibration-sheets/), not app code -- served so the
# Setup wizard can hand the operator a direct download link at the point they're needed.
CALIBRATION_SHEETS_DIR = Path(__file__).parent.parent.parent / "reference" / "calibration-sheets"

# Before any thread is started: a memory pool already made is not removed (#348).
images.limit_allocator()
photos_root().mkdir(parents=True, exist_ok=True)
experiments_root().mkdir(parents=True, exist_ok=True)
calibration_root().mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # The gap since the last tick is measured at start, before any photo (captures.py).
    record_app_start()
    # An export cut off by the previous stop can never finish (exports.py).
    database.fail_unfinished_exports(now=datetime.now(timezone.utc).isoformat())
    photo_scheduler = Scheduler()
    photo_scheduler.start()
    # Reads each photo for its trays after it is saved (#222).
    tray_reader = TrayReader()
    tray_reader.start()
    # Opened now, in the background, so health says whether a camera is attached and working
    # without waiting for the first photo (#252).
    CameraManager.open_in_background()
    yield
    # A scheduled photo already being taken finishes; the camera close below waits for it.
    photo_scheduler.stop(timeout_s=0)
    # A tag search under way is not waited for: its thread ends with the process.
    tray_reader.stop(timeout_s=0)
    record_app_stop()
    # An open still under way would start a camera program after the close below (#252).
    if not await run_in_threadpool(CameraManager.wait_for_open, SHUTDOWN_CAMERA_OPEN_WAIT_S):
        logger.warning("The camera was still opening at shutdown; it is not closed cleanly")
    # End the camera program cleanly, so the camera is closed rather than killed (#51).
    manager = CameraManager._instance
    close = getattr(manager._backend, "close", None) if manager is not None else None
    if close is not None:
        await run_in_threadpool(_close_camera_when_idle, manager, close)


# The launch command's --timeout-graceful-shutdown cancels a live stream that is still open, but a
# frame grab it has started goes on in its worker thread. Closing the camera program under that
# grab would read as a camera fault and restart it (#139), so the close waits for _call_lock. The
# wait is bounded above the longest camera call limit (camera_process.CALL_TIME_LIMITS_S).
SHUTDOWN_CAMERA_IDLE_WAIT_S = 120.0
# Above camera_process.OPEN_TIME_LIMIT_S (30 s) plus the lens replay after an open.
SHUTDOWN_CAMERA_OPEN_WAIT_S = 45.0


def _close_camera_when_idle(manager: CameraManager, close: Callable[[], None]) -> None:
    """Run `close` holding the manager's call lock, so no camera call is in flight under it."""
    acquired = manager._call_lock.acquire(timeout=SHUTDOWN_CAMERA_IDLE_WAIT_S)
    if not acquired:
        logger.error(
            "A camera call was still running after %.0f s at shutdown; closing the camera anyway",
            SHUTDOWN_CAMERA_IDLE_WAIT_S,
        )
    try:
        close()
    finally:
        if acquired:
            manager._call_lock.release()


app = FastAPI(title="NPEC Camera Rig", lifespan=_lifespan)


@app.exception_handler(CameraFaultError)
async def _camera_fault(_request: Request, exc: CameraFaultError) -> JSONResponse:
    """A camera call that did not finish in time, or a camera restarting or not reopened
    (camera_process.py): one answer for every route, in the shape HTTPException gives, so every
    page shows the message the way it shows its other errors."""
    return JSONResponse({"detail": str(exc)}, status_code=503)


# The errors the photo, calibration and validation modules raise for a request they cannot answer, each with
# the status a route used to give it (#182). Only these classes: a handler on LookupError or
# ValueError itself would turn a KeyError bug into a 404.
_DOMAIN_ERROR_STATUS = {
    CaptureRefError: 422,
    CaptureNotFoundError: 404,
    FrameMissingError: 409,
    CalibrationNotFoundError: 404,
    CalibrationUnreadableError: 422,
    SessionNotFoundError: 404,
    RoundNotFoundError: 404,
    ValidationRefusedError: 409,
}


async def _domain_error(_request: Request, exc: Exception) -> JSONResponse:
    """In the shape HTTPException gives, so every page shows the message as it shows the others."""
    status = next(_DOMAIN_ERROR_STATUS[k] for k in type(exc).__mro__ if k in _DOMAIN_ERROR_STATUS)
    return JSONResponse({"detail": str(exc)}, status_code=status)


for _error in _DOMAIN_ERROR_STATUS:
    app.add_exception_handler(_error, _domain_error)
app.mount("/photos", StaticFiles(directory=str(photos_root())), name="photos")
# Not /experiments: that prefix is the experiments page.
app.mount(
    "/experiment-files", StaticFiles(directory=str(experiments_root())), name="experiment_files"
)
# PLAN.md M2 section A: calibration is "frozen, versioned, exportable" -- this is the export.
# Serves the timestamped artifact JSON and its plots. Its photo is a rig photo, under /photos
# (calibration_store.calibration_frame_url).
app.mount("/calibration/files", StaticFiles(directory=str(calibration_root())), name="calibration_files")
# Shared CSS (and any future shared JS) for the plain multi-page static frontend -- no build step,
# no templating, just files served as-is alongside the page routes below.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount(
    "/reference/calibration-sheets",
    StaticFiles(directory=str(CALIBRATION_SHEETS_DIR)),
    name="calibration_sheets",
)

# One route file per feature (#181). Each feature's routes keep their order within their file;
# no two files serve the same path.
app.include_router(shell.router)
app.include_router(focus.router)
app.include_router(experiments.router)
app.include_router(gallery.router)
app.include_router(calibration.router)
app.include_router(validation.router)
