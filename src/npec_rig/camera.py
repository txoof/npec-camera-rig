"""Camera access: the CameraManager singleton, the picamera2 and synthetic backends, and
focus scoring (Laplacian variance) used by the focus aid.
"""

from __future__ import annotations

import io
import logging
import os
from abc import ABC, abstractmethod
from threading import Lock
from typing import ClassVar

import numpy as np
from PIL import Image

from npec_rig.settings import load_settings, save_setting

logger = logging.getLogger(__name__)

DEFAULT_LENS_POSITION = 1.0
MAIN_SIZE = (1536, 1152)  # (width, height) — must match Picamera2Backend's video config `main`
LORES_SIZE = (320, 240)
DEFAULT_ROI_SIZE = 200
SIMULATED_AUTOFOCUS_POSITION = 6.3  # synthetic backend has no real optics; matches the old rig's
# known-good position so the UI has something plausible to demo against

# Controls exposed generically (slice 4): ranges are probed from picamera2's own
# `camera_controls` at runtime, not hardcoded — LensPosition's max has already been observed to
# change between probes (15.0 during M0, 32.0 later), so a hardcoded range would have been
# actively wrong here, not just lazy.
CONTROL_NAMES = ("ExposureTime", "AnalogueGain", "AwbEnable", "AeEnable", "LensPosition")
_CACHED_CONTROLS = ("AwbEnable", "AeEnable")  # not echoed by capture_metadata() — see below

SYNTHETIC_CONTROL_RANGES = {
    "ExposureTime": (1, 66666, 20000),
    "AnalogueGain": (1.0, 16.0, 1.0),
    "AwbEnable": (False, True, True),
    "AeEnable": (False, True, True),
    "LensPosition": (0.0, 15.0, DEFAULT_LENS_POSITION),
}

# capture_full_res's metadata shape, shared so the synthetic backend can't drift from what real
# hardware reports — code written against one backend must behave the same on the other.
SENSOR_METADATA_FIELDS = ("SensorTimestamp", "ExposureTime", "AnalogueGain", "ColourGains", "LensPosition")


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
        """Set manual lens position (dioptres)."""

    @abstractmethod
    def get_lens_position(self) -> float:
        """Current lens position (dioptres)."""

    @abstractmethod
    def autofocus(self) -> tuple[bool, float]:
        """Run one hardware autofocus cycle, then return to manual. (success, lens_position)."""

    @abstractmethod
    def available_controls(self) -> dict[str, tuple]:
        """{control_name: (min, max, default)}, probed from the camera, not hardcoded."""

    @abstractmethod
    def get_controls(self) -> dict:
        """Current value of each control in `available_controls`."""

    @abstractmethod
    def set_control(self, name: str, value: object) -> None:
        """Set one named control to value."""


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
        self._controls = {
            name: default
            for name, (_, _, default) in SYNTHETIC_CONTROL_RANGES.items()
            if name != "LensPosition"
        }

    def capture_array(self) -> np.ndarray:
        return self._pattern(self._width, self._height)

    def capture_preview_array(self) -> np.ndarray:
        return self._pattern(self._preview_width, self._preview_height)

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        # Same key set as Picamera2Backend.capture_full_res (SENSOR_METADATA_FIELDS) — no real
        # optics to report ColourGains/SensorTimestamp from, so those two are fixed placeholders.
        metadata = {
            "SensorTimestamp": 0,
            "ExposureTime": self._controls["ExposureTime"],
            "AnalogueGain": self._controls["AnalogueGain"],
            "ColourGains": (1.0, 1.0),
            "LensPosition": self._lens_position,
        }
        return self._pattern(self._width, self._height), metadata

    def set_lens_position(self, value: float) -> None:
        self._lens_position = value

    def get_lens_position(self) -> float:
        return self._lens_position

    def autofocus(self) -> tuple[bool, float]:
        self._lens_position = SIMULATED_AUTOFOCUS_POSITION
        return True, self._lens_position

    def available_controls(self) -> dict[str, tuple]:
        return dict(SYNTHETIC_CONTROL_RANGES)

    def get_controls(self) -> dict:
        return {**self._controls, "LensPosition": self._lens_position}

    def set_control(self, name: str, value: object) -> None:
        if name == "LensPosition":
            self._lens_position = value
        else:
            self._controls[name] = value

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
        # Pin an explicit format on both streams rather than trusting the negotiated default
        # (unspecified, `lores` picked YUV420 planar — see git history for that bug). "RGB888"
        # is confirmed correct here, checked directly against picamera2 (not assumed): a
        # channel-swap test (RGB888 vs BGR888 arrays, compared against each other reversed)
        # showed RGB888 gives genuine R,G,B order, and a known-neutral white reference in the
        # same frame comes back neutral (no colour-cast bug either). Do not switch this to
        # "BGR888" without re-running that check — it was tried and measured wrong.
        self._video_config = self._picam2.create_video_configuration(
            main={"size": MAIN_SIZE, "format": "RGB888"},
            lores={"size": LORES_SIZE, "format": "RGB888"},
        )
        self._picam2.configure(self._video_config)
        self._picam2.set_controls({"AfMode": 0, "LensPosition": DEFAULT_LENS_POSITION})
        self._picam2.start()
        # AwbEnable/AeEnable are write-only in practice: checked directly (not assumed) —
        # capture_metadata() reports None for both, unlike ExposureTime/AnalogueGain/
        # LensPosition, which it reports correctly. Cache the last value we set instead.
        probed = self._picam2.camera_controls
        self._control_cache = {
            name: (True if probed[name][2] is None else probed[name][2])
            for name in _CACHED_CONTROLS
            if name in probed
        }

    def capture_array(self) -> np.ndarray:
        return self._picam2.capture_array("main")

    def capture_preview_array(self) -> np.ndarray:
        return self._picam2.capture_array("lores")

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        still_config = self._picam2.create_still_configuration(main={"format": "RGB888"})
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
        sensor_metadata = {key: metadata.get(key) for key in SENSOR_METADATA_FIELDS}
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

    def available_controls(self) -> dict[str, tuple]:
        probed = self._picam2.camera_controls
        return {name: probed[name] for name in CONTROL_NAMES if name in probed}

    def get_controls(self) -> dict:
        metadata = self._picam2.capture_metadata()
        return {
            name: self._control_cache[name] if name in _CACHED_CONTROLS else metadata.get(name)
            for name in CONTROL_NAMES
        }

    def set_control(self, name: str, value: object) -> None:
        self._picam2.set_controls({name: value})
        if name in _CACHED_CONTROLS:
            self._control_cache[name] = value


def array_to_jpeg(frame: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(frame).convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()


def to_grayscale(frame: np.ndarray) -> np.ndarray:
    return frame[..., 0] * 0.299 + frame[..., 1] * 0.587 + frame[..., 2] * 0.114


def _laplacian(gray: np.ndarray) -> np.ndarray:
    """Discrete Laplacian at each interior pixel (edges excluded, no padding)."""
    return (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )


def laplacian_variance(gray: np.ndarray) -> float:
    """Sharpness score: variance of the discrete Laplacian. Higher is sharper."""
    return float(_laplacian(gray).var())


PEAKING_THRESHOLD = 30.0  # Laplacian magnitude cutoff for "sharp enough to be in focus"
PEAKING_COLOR = (255, 0, 255)  # magenta — doesn't occur naturally in a plant/paper/table scene


def peaking_overlay(crop: np.ndarray, threshold: float = PEAKING_THRESHOLD) -> np.ndarray:
    """Highlight high-contrast edges in a bright color, as a visual focus check."""
    gray = to_grayscale(crop)
    edge_mask = np.abs(_laplacian(gray)) > threshold
    overlay = crop.copy()
    overlay[1:-1, 1:-1][edge_mask] = PEAKING_COLOR
    return overlay


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
        self._peaking_enabled = False
        self._apply_persisted_settings()

    def _apply_persisted_settings(self) -> None:
        # The console loads last-used values rather than defaults (slice 4 requirement — the
        # old UI's known gap). Applied directly against the backend, not through set_control,
        # so loading a value doesn't immediately re-save it.
        #
        # AeEnable/AwbEnable must be applied first: on a fresh start AE is on by default, and
        # while it's on it silently overrides any AnalogueGain/ExposureTime write on the very
        # next frame — confirmed on real hardware, this isn't hypothetical. Applying the
        # enable/disable toggles before the dependent values avoids that race.
        persisted = load_settings()
        available = self._backend.available_controls()
        ordered_names = sorted(persisted, key=lambda name: name not in ("AeEnable", "AwbEnable"))
        for name in ordered_names:
            if name in available:
                self._backend.set_control(name, persisted[name])

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
        save_setting("LensPosition", value)

    def get_lens_position(self) -> float:
        with self._call_lock:
            return self._backend.get_lens_position()

    def autofocus(self) -> dict:
        with self._call_lock:
            success, lens_position = self._backend.autofocus()
        save_setting("LensPosition", lens_position)
        return {"success": success, "lens_position": lens_position}

    def available_controls(self) -> dict[str, tuple]:
        with self._call_lock:
            return self._backend.available_controls()

    def get_controls(self) -> dict:
        with self._call_lock:
            return self._backend.get_controls()

    def set_control(self, name: str, value: object) -> dict:
        with self._call_lock:
            self._backend.set_control(name, value)
            values = self._backend.get_controls()
        save_setting(name, value)
        return values

    def get_roi(self) -> dict:
        with self._call_lock:
            return dict(self._roi)

    def set_roi(self, x: int, y: int, size: int | None = None) -> dict:
        with self._call_lock:
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
        if self._peaking_enabled:
            crop = peaking_overlay(crop)
        return array_to_jpeg(crop)

    def get_peaking(self) -> dict:
        return {"enabled": self._peaking_enabled}

    def set_peaking(self, enabled: bool) -> dict:
        self._peaking_enabled = enabled
        return self.get_peaking()

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
