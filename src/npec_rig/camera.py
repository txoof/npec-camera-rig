"""Camera access: the CameraManager singleton, the picamera2 and synthetic backends, and
focus scoring (Laplacian variance) used by the focus aid.
"""

from __future__ import annotations

import io
import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
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

# A restart-persisted focus confirmation is only trusted if the restored LensPosition still
# matches the position it was confirmed at (settings.py values, not a live metadata read -- see
# _restore_focus_confirmation). This tolerance absorbs float round-tripping through
# capture_metadata() only (measured 2026-09-28: a value set to 6.2 reads back as
# 6.199999809265137, consistently) -- it is not a claim that focus is forgiving to within this
# much drift; 0.01 dioptres is far smaller than a real, operator-meaningful lens move.
FOCUS_CONFIRM_POSITION_TOLERANCE = 0.01

# preview.mjpg and focus/roi.mjpg grab one frame per loop iteration, under _call_lock, forever
# (see CameraBusyError). A one-shot control (autofocus, capture) is allowed to block on this
# lock indefinitely -- that's correct, the operator is waiting on that specific call. A stream
# iteration is not a one-shot call: if it blocks forever, so does the thread anyio lent it, for
# good, because that thread is behind a cancellation-shielded call the client disconnecting
# cannot interrupt (confirmed against the installed anyio/Starlette source, 2026-09-29). Bounding
# the wait means a stuck lock degrades one stream to occasional skipped frames instead of
# quietly eating one more worker thread per attempt until the shared pool -- used by every other
# route too -- is exhausted and the whole server stops responding.
STREAM_LOCK_TIMEOUT = 2.0


class CameraBusyError(RuntimeError):
    """Raised by a streaming frame grab (preview_jpeg, roi_crop_jpeg) that could not acquire
    _call_lock within STREAM_LOCK_TIMEOUT. Callers should skip the frame, not block on it."""


# Controls exposed generically (slice 4): ranges are probed from picamera2's own
# `camera_controls` at runtime, not hardcoded — LensPosition's max has already been observed to
# change between probes (15.0 during M0, 32.0 later), so a hardcoded range would have been
# actively wrong here, not just lazy.
CONTROL_NAMES = ("ExposureTime", "AnalogueGain", "AwbEnable", "AeEnable", "LensPosition")
_CACHED_CONTROLS = ("AwbEnable", "AeEnable")  # not echoed by capture_metadata() — see below
# Only meaningful while AE is off — see Picamera2Backend.set_control / SyntheticBackend.set_control.
_AE_DEPENDENT_CONTROLS = ("ExposureTime", "AnalogueGain")

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
        if name in _AE_DEPENDENT_CONTROLS and self._controls.get("AeEnable"):
            # Mirrors Picamera2Backend.set_control's guard so this invariant is testable
            # without hardware — see its docstring for why.
            return
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
        # `main` gets NO explicit format. Confirmed 2026-09-21 against a known-color
        # real-world reference, twice over (first wrongly, then correctly -- see TODO.md for
        # the full account): explicitly keying "format" on a stream -- "RGB888" and "BGR888"
        # were both tried -- puts this picamera2/libcamera build on a different, buggy
        # internal path that comes out with swapped color, regardless of which string is
        # named. Left unconstrained, `main` negotiates its own default (logged as "XBGR8888",
        # 4 channels) and the array it hands back is genuinely R,G,B(,padding) in that channel
        # order, DESPITE that log name suggesting B,G,R -- verified directly against the
        # tote, not inferred from the label.
        # `lores` still needs a format pinned, or it negotiates YUV420 planar and produces
        # garbage (the original reason this pinning existed at all -- see git history).
        # "XBGR8888" here too, for the same reason as `main`'s natural default: confirmed
        # correct, despite the name, with no reordering.
        # array_to_jpeg()/to_grayscale() below treat the first 3 channels as literal R,G,B and
        # ignore any 4th (padding) channel -- no reversal, for either stream.
        self._video_config = self._picam2.create_video_configuration(
            main={"size": MAIN_SIZE},
            lores={"size": LORES_SIZE, "format": "XBGR8888"},
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
        # No explicit format here either, for the same reason as `main` above -- unconstrained,
        # this negotiates plain 3-channel (logged as "BGR888", genuinely R,G,B as delivered)
        # and comes out correct against a known-color reference; explicitly keying "format"
        # does not, regardless of which string is named.
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
            # configure() replaces picamera2's live Controls with just the new config's own
            # (near-empty) controls dict — AeEnable/AwbEnable are silently dropped, and nothing
            # else re-applies them. Confirmed on real hardware: after a full-res capture, the
            # camera reverts to its config/tuning-file default while this app's own cache still
            # claims AE/AWB are on, so the image can go stuck/washed-out without the checkbox
            # ever changing. Restore whatever this app last believed AwbEnable/AeEnable were —
            # via set_control, not a raw set_controls call, so re-enabling AE here also releases
            # the ExposureTimeMode/AnalogueGainMode manual latch the same way a live checkbox
            # toggle does (see set_control below). A manually-set ExposureTime/AnalogueGain
            # while AE was off is NOT restored here — those aren't cached (see TODO.md).
            for name, value in dict(self._control_cache).items():
                self.set_control(name, value)
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
        if name in _AE_DEPENDENT_CONTROLS and self._control_cache.get("AeEnable"):
            # Manual ExposureTime/AnalogueGain only makes sense while AE is off — writing
            # either while AE is on would silently re-arm picamera2's ExposureTimeMode/
            # AnalogueGainMode manual latch behind AE's back (see the AeEnable branch below).
            # Guarded once, here, so every caller — the HTTP endpoint, the persisted-settings
            # replay at startup, the post-full-res-capture restore, a stale browser tab with
            # sliders still enabled — is covered by one rule instead of each needing to know it.
            return
        self._picam2.set_controls({name: value})
        if name in _CACHED_CONTROLS:
            self._control_cache[name] = value
        if name == "AeEnable" and value:
            # picamera2 latches ExposureTimeMode/AnalogueGainMode to manual the moment any
            # nonzero ExposureTime/AnalogueGain is sent (request.py's CompletedRequest.release),
            # and AeEnable alone does not clear that — confirmed against the installed picamera2
            # source. 0 is picamera2's own sentinel for "return to auto," not a real exposure
            # value (no range validation rejects it), so this releases the latch outright.
            self._picam2.set_controls({"ExposureTime": 0, "AnalogueGain": 0})


def array_to_jpeg(frame: np.ndarray) -> bytes:
    """`frame`'s first 3 channels are literally R,G,B, in that order, with an optional 4th
    (unused padding) channel ignored -- verified directly against a known-color real-world
    reference on 2026-09-21, not inferred from picamera2's own format name (which is
    misleading here: it logs "BGR888"/"XBGR8888", but does not deliver that byte order --
    see Picamera2Backend.__init__). `frame[..., :3]` takes the first three channels
    unreordered; do not add a reversal here without re-running that same direct check --
    exactly this reversal was tried and measured wrong once already (TODO.md has the account).
    """
    buffer = io.BytesIO()
    Image.fromarray(frame[..., :3]).convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()


def to_grayscale(frame: np.ndarray) -> np.ndarray:
    """`frame`'s first 3 channels are R,G,B -- see array_to_jpeg. Standard luminance weights,
    applied to the matching channel: 0.299 to red (channel 0), 0.114 to blue (channel 2). Any
    4th (padding) channel is simply never referenced.
    """
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
    """Highlight high-contrast edges in a bright color, as a visual focus check.

    PEAKING_COLOR is symmetric (255, 0, 255) -- magenta reads the same whether the first and
    third values are red/blue or blue/red, so it's correct regardless. Written to only the
    first 3 channels: `crop` may be 3-channel or have a trailing unused padding channel (from
    the video config's "XBGR8888") -- see array_to_jpeg.
    """
    gray = to_grayscale(crop)
    edge_mask = np.abs(_laplacian(gray)) > threshold
    overlay = crop.copy()
    overlay[1:-1, 1:-1][edge_mask, :3] = PEAKING_COLOR
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
        # A persisted manual ExposureTime/AnalogueGain is only meaningful when AE was off when
        # it was saved — if AE is (or defaults to) on, replaying one would re-latch picamera2's
        # manual-mode controls behind AE's back. Applying AeEnable/AwbEnable first means the
        # backend's own cache reflects the real AE state before ExposureTime/AnalogueGain are
        # replayed, so Picamera2Backend.set_control's guard catches this correctly even when
        # AeEnable was never explicitly persisted (missing key, not "False") — confirmed against
        # a real stale ExposureTime sitting in this rig's own DB alongside AeEnable=true.
        persisted = load_settings()
        available = self._backend.available_controls()
        ordered_names = sorted(persisted, key=lambda name: name not in ("AeEnable", "AwbEnable"))
        for name in ordered_names:
            if name in available:
                self._backend.set_control(name, persisted[name])
        self._restore_focus_confirmation(persisted)

    def _restore_focus_confirmation(self, persisted: dict) -> None:
        """Trust a persisted "focus confirmed" flag only if the LensPosition it was confirmed
        at still matches the persisted current LensPosition -- measured 2026-09-28 (a real
        kill+relaunch restart, sharpness score at the same LensPosition matched within 2% of
        its pre-restart value), replaying the same number really does return the same physical
        focus. A mismatch means something moved the lens since the last confirm and the
        confirmation must not carry over.
        """
        if not persisted.get("FocusConfirmed"):
            return
        confirmed_position = persisted.get("FocusConfirmedLensPosition")
        current_position = persisted.get("LensPosition")
        if (
            confirmed_position is not None
            and current_position is not None
            and abs(confirmed_position - current_position) < FOCUS_CONFIRM_POSITION_TOLERANCE
        ):
            self._locked_lens_position = current_position

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

    @contextmanager
    def _stream_call_lock(self, name: str) -> Iterator[None]:
        """Hold _call_lock for a streaming frame grab, bounded by STREAM_LOCK_TIMEOUT --
        raises CameraBusyError instead of blocking indefinitely. Only for preview_jpeg and
        roi_crop_jpeg; every other caller is a one-shot action that should keep waiting."""
        if not self._call_lock.acquire(timeout=STREAM_LOCK_TIMEOUT):
            raise CameraBusyError(name)
        try:
            yield
        finally:
            self._call_lock.release()

    def preview_jpeg(self) -> bytes:
        """Raises CameraBusyError if _call_lock isn't free within STREAM_LOCK_TIMEOUT."""
        with self._stream_call_lock("preview_jpeg"):
            return array_to_jpeg(self._backend.capture_preview_array())

    def capture_array(self) -> np.ndarray:
        """Raw main-stream frame, for callers that need pixels rather than a JPEG (e.g. the live
        reorientation aid's tag detection -- the lores stream is too low-resolution for
        `detect_tags` to find corner tags at all, confirmed on real hardware)."""
        with self._call_lock:
            return self._backend.capture_array()

    def capture_preview_array(self) -> np.ndarray:
        """Raw lores frame, for callers that need pixels rather than a JPEG."""
        with self._call_lock:
            return self._backend.capture_preview_array()

    def set_lens_position(self, value: float) -> None:
        with self._call_lock:
            self._backend.set_lens_position(value)
        save_setting("LensPosition", value)
        # A manual move invalidates whatever focus was locked -- the operator has to
        # re-confirm and re-lock before calibration will trust it again. Persisted too, not
        # just in-memory, so a restart right after a move doesn't resurrect the old confirm.
        self._locked_lens_position = None
        save_setting("FocusConfirmed", False)

    def get_lens_position(self) -> float:
        with self._call_lock:
            return self._backend.get_lens_position()

    def autofocus(self) -> dict:
        with self._call_lock:
            success, lens_position = self._backend.autofocus()
        save_setting("LensPosition", lens_position)
        self._locked_lens_position = None
        save_setting("FocusConfirmed", False)
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
        """Raises CameraBusyError if _call_lock isn't free within STREAM_LOCK_TIMEOUT."""
        with self._stream_call_lock("roi_crop_jpeg"):
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
        # Persisted so a restart (dev reload, crash, future systemd restart-on-failure) doesn't
        # silently drop a real confirmation -- see _restore_focus_confirmation for the safety
        # check that only trusts this if the lens is verifiably still where it was confirmed.
        save_setting("FocusConfirmed", True)
        save_setting("FocusConfirmedLensPosition", lens_position)
        return self.focus_status()

    def unlock_focus(self) -> dict:
        self._locked_lens_position = None
        save_setting("FocusConfirmed", False)
        return self.focus_status()

    def focus_status(self) -> dict:
        return {
            "locked": self._locked_lens_position is not None,
            "lens_position": self._locked_lens_position,
        }

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        with self._call_lock:
            return self._backend.capture_full_res()
