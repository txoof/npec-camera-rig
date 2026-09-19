import time
from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from npec_rig.camera import CameraManager
from npec_rig.captures import captures_root, list_recent_captures, save_capture

STATIC_DIR = Path(__file__).parent / "static"
PREVIEW_BOUNDARY = b"frame"
PREVIEW_FPS_LIMIT = 10.0
ROI_STREAM_FPS_LIMIT = 5.0

captures_root().mkdir(parents=True, exist_ok=True)

app = FastAPI(title="NPEC Camera Rig")
app.mount("/captures", StaticFiles(directory=str(captures_root())), name="captures")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """The camera console page."""
    return (STATIC_DIR / "index.html").read_text()


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
