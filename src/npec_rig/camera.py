from __future__ import annotations

import io
import logging
import os
from abc import ABC, abstractmethod
from threading import Lock
from typing import ClassVar

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

DEFAULT_LENS_POSITION = 1.0
MAIN_SIZE = (1536, 1152)  # (width, height) — must match Picamera2Backend's video config `main`
LORES_SIZE = (320, 240)
DEFAULT_ROI_SIZE = 200
LENS_POSITION_RANGE = (0.0, 15.0)  # dioptres, per M0 probe
LENS_POSITION_STEPS = 1024  # actuator's real step count, measured via v4l2-ctl focus_absolute
SIMULATED_AUTOFOCUS_POSITION = 6.3  # synthetic backend has no real optics; matches the old rig's
# known-good position so the UI has something plausible to demo against


class CameraBackend(ABC):
    """A source of frames and focus control. Real hardware or synthetic, same interface."""

    @abstractmethod
    def capture_array(self) -> np.ndarray:
        """A full frame from the main stream, for on-demand snapshots and the focus aid."""

    @abstractmethod
    def capture_preview_array(self) -> np.ndarray:
        """A small frame from the lores stream, for the live preview."""

    @abstractmethod
    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        """A deliberate, full-sensor-resolution still plus its capture metadata."""

    @abstractmethod
    def set_lens_position(self, value: float) -> None:
        ...

    @abstractmethod
    def get_lens_position(self) -> float:
        ...

    @abstractmethod
    def autofocus(self) -> tuple[bool, float]:
        """Run one hardware autofocus cycle, then return to manual. (success, lens_position)."""


class SyntheticBackend(CameraBackend):
    """Deterministic test pattern. No hardware required."""

    def __init__(
        self,
        width: int = MAIN_SIZE[0],
        height: int = MAIN_SIZE[1],
        preview_width: int = LORES_SIZE[0],
        preview_height: int = LORES_SIZE[1],
    ) -> None:
        self._width = width
        self._height = height
        self._preview_width = preview_width
        self._preview_height = preview_height
        self._lens_position = DEFAULT_LENS_POSITION

    def capture_array(self) -> np.ndarray:
        return self._pattern(self._width, self._height)

    def capture_preview_array(self) -> np.ndarray:
        return self._pattern(self._preview_width, self._preview_height)

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        return self._pattern(self._width, self._height), {"backend": "synthetic"}

    def set_lens_position(self, value: float) -> None:
        self._lens_position = value

    def get_lens_position(self) -> float:
        return self._lens_position

    def autofocus(self) -> tuple[bool, float]:
        self._lens_position = SIMULATED_AUTOFOCUS_POSITION
        return True, self._lens_position

    @staticmethod
    def _pattern(width: int, height: int) -> np.ndarray:
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 1] = 180
        return frame


class Picamera2Backend(CameraBackend):
    """Wraps picamera2. The only code in this project touching the camera.

    Runs one dual-stream video configuration: a mid-resolution `main` for on-demand
    snapshots and the focus aid, and a small `lores` for the MJPEG live preview. Full-sensor
    still capture is a separate, deliberate mode switch used only by `capture_full_res`,
    since full-sensor readout tops out at ~3 fps (see M0 probe) and can't share the
    continuous preview stream.
    """

    def __init__(self) -> None:
        from picamera2 import Picamera2

        self._picam2 = Picamera2()
        self._video_config = self._picam2.create_video_configuration(
            main={"size": MAIN_SIZE},
            lores={"size": LORES_SIZE},
            encode="lores",
        )
        self._picam2.configure(self._video_config)
        self._picam2.set_controls({"AfMode": 0, "LensPosition": DEFAULT_LENS_POSITION})
        self._picam2.start()

    def capture_array(self) -> np.ndarray:
        return self._picam2.capture_array("main")

    def capture_preview_array(self) -> np.ndarray:
        return self._picam2.capture_array("lores")

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        still_config = self._picam2.create_still_configuration()
        self._picam2.stop()
        self._picam2.configure(still_config)
        self._picam2.start()
        try:
            array = self._picam2.capture_array("main")
            metadata = self._picam2.capture_metadata()
        finally:
            self._picam2.stop()
            self._picam2.configure(self._video_config)
            self._picam2.start()
        sensor_metadata = {
            key: metadata.get(key)
            for key in (
                "SensorTimestamp",
                "ExposureTime",
                "AnalogueGain",
                "ColourGains",
                "LensPosition",
            )
        }
        return array, sensor_metadata

    def set_lens_position(self, value: float) -> None:
        self._picam2.set_controls({"LensPosition": value})

    def get_lens_position(self) -> float:
        metadata = self._picam2.capture_metadata()
        return float(metadata.get("LensPosition", DEFAULT_LENS_POSITION))

    def autofocus(self) -> tuple[bool, float]:
        success = self._picam2.autofocus_cycle(wait=True)
        lens_position = self.get_lens_position()
        # autofocus_cycle leaves AfMode in Auto; the rig always runs manual so a fixed
        # focus can't drift or hunt mid-experiment (see PLAN.md M1/M2).
        self._picam2.set_controls({"AfMode": 0})
        return bool(success), lens_position


def array_to_jpeg(frame: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(frame).convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()


def to_grayscale(frame: np.ndarray) -> np.ndarray:
    return frame[..., 0] * 0.299 + frame[..., 1] * 0.587 + frame[..., 2] * 0.114


def laplacian_variance(gray: np.ndarray) -> float:
    """Sharpness score: variance of the discrete Laplacian. Higher is sharper."""
    laplacian = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    return float(laplacian.var())


def crop_roi(frame: np.ndarray, x: int, y: int, size: int) -> np.ndarray:
    height, width = frame.shape[:2]
    size = max(1, min(size, width, height))
    half = size // 2
    x0 = max(0, min(x - half, width - size))
    y0 = max(0, min(y - half, height - size))
    return frame[y0 : y0 + size, x0 : x0 + size]


def _default_backend() -> CameraBackend:
    if os.environ.get("NPEC_RIG_SYNTHETIC_CAMERA"):
        return SyntheticBackend()
    try:
        return Picamera2Backend()
    except (ImportError, RuntimeError) as exc:
        logger.warning("No camera hardware available (%s); using synthetic backend", exc)
        return SyntheticBackend()


class CameraManager:
    """Singleton owning the active camera backend. Serializes hardware access."""

    _instance: ClassVar[CameraManager | None] = None
    _instance_lock: ClassVar[Lock] = Lock()

    def __init__(self, backend: CameraBackend) -> None:
        self._backend = backend
        self._call_lock = Lock()
        width, height = MAIN_SIZE
        self._roi = {"x": width // 2, "y": height // 2, "size": DEFAULT_ROI_SIZE}
        self._locked_lens_position: float | None = None

    @classmethod
    def instance(cls) -> CameraManager:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(_default_backend())
        return cls._instance

    @classmethod
    def set_instance(cls, manager: CameraManager) -> None:
        with cls._instance_lock:
            cls._instance = manager

    def snapshot_jpeg(self) -> bytes:
        with self._call_lock:
            return array_to_jpeg(self._backend.capture_array())

    def preview_jpeg(self) -> bytes:
        with self._call_lock:
            return array_to_jpeg(self._backend.capture_preview_array())

    def set_lens_position(self, value: float) -> None:
        with self._call_lock:
            self._backend.set_lens_position(value)

    def get_lens_position(self) -> float:
        with self._call_lock:
            return self._backend.get_lens_position()

    def autofocus(self) -> dict:
        with self._call_lock:
            success, lens_position = self._backend.autofocus()
        return {"success": success, "lens_position": lens_position}

    def get_roi(self) -> dict:
        return dict(self._roi)

    def set_roi(self, x: int, y: int, size: int | None = None) -> dict:
        self._roi["x"] = x
        self._roi["y"] = y
        if size is not None:
            self._roi["size"] = size
        return dict(self._roi)

    def focus_score(self) -> float:
        with self._call_lock:
            frame = self._backend.capture_array()
        crop = crop_roi(frame, self._roi["x"], self._roi["y"], self._roi["size"])
        return laplacian_variance(to_grayscale(crop))

    def roi_crop_jpeg(self) -> bytes:
        with self._call_lock:
            frame = self._backend.capture_array()
        crop = crop_roi(frame, self._roi["x"], self._roi["y"], self._roi["size"])
        return array_to_jpeg(crop)

    def lock_focus(self) -> dict:
        lens_position = self.get_lens_position()
        self._locked_lens_position = lens_position
        return self.focus_status()

    def unlock_focus(self) -> dict:
        self._locked_lens_position = None
        return self.focus_status()

    def focus_status(self) -> dict:
        return {
            "locked": self._locked_lens_position is not None,
            "lens_position": self._locked_lens_position,
        }

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        with self._call_lock:
            return self._backend.capture_full_res()
