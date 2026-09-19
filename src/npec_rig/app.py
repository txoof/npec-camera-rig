import time
from collections.abc import Callable, Iterator
from pathlib import Path

from fastapi import FastAPI
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
    return (STATIC_DIR / "index.html").read_text()


@app.get("/snapshot.jpg")
def snapshot() -> Response:
    jpeg = CameraManager.instance().snapshot_jpeg()
    return Response(content=jpeg, media_type="image/jpeg")


def _mjpeg_frames(jpeg_source: Callable[[], bytes], fps_limit: float) -> Iterator[bytes]:
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
    return StreamingResponse(
        _mjpeg_frames(jpeg_source, fps_limit),
        media_type=f"multipart/x-mixed-replace; boundary={PREVIEW_BOUNDARY.decode()}",
    )


@app.get("/preview.mjpg")
def preview() -> StreamingResponse:
    manager = CameraManager.instance()
    return _mjpeg_response(manager.preview_jpeg, PREVIEW_FPS_LIMIT)


class LensPosition(BaseModel):
    value: float = Field(ge=0.0, le=15.0)


@app.get("/controls/lens-position")
def get_lens_position() -> LensPosition:
    return LensPosition(value=CameraManager.instance().get_lens_position())


@app.post("/controls/lens-position")
def set_lens_position(position: LensPosition) -> LensPosition:
    CameraManager.instance().set_lens_position(position.value)
    return position


@app.post("/focus/autofocus")
def autofocus() -> dict:
    return CameraManager.instance().autofocus()


class RoiUpdate(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    size: int | None = Field(default=None, gt=0)


@app.get("/focus/roi")
def get_roi() -> dict:
    return CameraManager.instance().get_roi()


@app.post("/focus/roi")
def set_roi(roi: RoiUpdate) -> dict:
    return CameraManager.instance().set_roi(roi.x, roi.y, roi.size)


@app.get("/focus/score")
def focus_score() -> dict:
    return {"score": CameraManager.instance().focus_score()}


@app.get("/focus/roi.mjpg")
def focus_roi_stream() -> StreamingResponse:
    manager = CameraManager.instance()
    return _mjpeg_response(manager.roi_crop_jpeg, ROI_STREAM_FPS_LIMIT)


@app.get("/focus/status")
def focus_status() -> dict:
    return CameraManager.instance().focus_status()


@app.post("/focus/lock")
def lock_focus() -> dict:
    return CameraManager.instance().lock_focus()


@app.post("/focus/unlock")
def unlock_focus() -> dict:
    return CameraManager.instance().unlock_focus()


@app.post("/capture")
def capture() -> dict:
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
    return list_recent_captures(limit=limit)
