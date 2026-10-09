"""Camera access: the CameraManager singleton, the picamera2 and synthetic backends, and
focus scoring (Laplacian variance) used by the focus aid.
"""

from __future__ import annotations

import io
import logging
import os
import time
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
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
# Every lens move that matters for measurement (locking focus, restoring it at startup) takes one
# path, `CameraManager._drive_lens`: step to LENS_APPROACH_OFFSET below the target, pause, set the
# target, then wait until the camera reports it. Measured 2026-10-01: the size of the central low
# reading depends on the lens position (about 1.2 points of area per 0.1) and on how the lens got
# there, and after a full-res capture the camera reports a move up to about 45 s late. One way of
# getting there, confirmed, keeps that error the same every time, so validation can measure it.
LENS_APPROACH_OFFSET = 0.3
LENS_APPROACH_PAUSE_S = 1.0
# How long every lens command waits for the camera to report the new position before the app says
# the lens is not responding. A decision, not a measurement: measured 2026-10-06 (TODO.md, "Lens
# stops responding after a full-res capture"), a working lens reports a new position within 0.6 s,
# and a stuck one never does (90 s); 5 s leaves room for a large move without a long silent wait.
# It was 60 s while the camera could report a move up to about 45 s late after a full-res capture;
# since the camera is reopened before any lens command that follows a capture (prepare_lens), that
# lag is the fault this detects.
LENS_SETTLE_TIMEOUT_S = 5.0
# How long one hardware autofocus cycle may hold the camera. picamera2's own wait has no limit:
# if the scan never starts (seen after a pipeline reconfigure, TODO.md "wedges the whole camera
# pipeline"), every camera call queues behind it until a restart. Same bound as a focus lock,
# which can also take up to a minute after a full-res capture; not a measured autofocus time
# (each cycle's duration is logged so one can be measured).
AUTOFOCUS_TIMEOUT_S = 60.0
# The share of that bound for reading the lens position once the cycle is done: one frame's
# metadata, so a few seconds is generous, and scan plus read together stay within the bound.
AUTOFOCUS_METADATA_TIMEOUT_S = 5.0
LENS_POLL_INTERVAL_S = 0.25
LENS_REPORT_TOLERANCE = 0.005

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


class CameraFaultError(RuntimeError):
    """The camera program (camera_process.py) cannot answer: a call did not finish in time, or the
    camera is being restarted or could not be reopened. The message is for the operator."""


class CameraStuckError(CameraFaultError):
    """A camera call did not finish within its time limit. The camera program was ended and is
    being restarted (#51)."""


class CameraUnavailableError(CameraFaultError):
    """The camera is restarting after a fault, or could not be reopened. Raised at once, without
    waiting, so no caller holds the camera lock for a camera that cannot answer."""


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

    def prepare_lens(self) -> None:
        """Make sure the next lens write is followed. Called right before every lens command
        (CameraManager); nothing to do unless a backend needs it (Picamera2Backend)."""

    def reset(self) -> None:
        """Close and reopen the camera connection, which is also what controls the lens. Nothing
        to do for a camera without one."""

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
        hang_file: str | None = None,
        fail_open_file: str | None = None,
    ) -> None:
        # Test switches for the camera program (camera_process.py), set by file so a test can
        # throw them while the camera runs in another process. `hang_file`: the next call whose
        # name is in the file (or any call, for "*") hangs, once: the file is removed, so the
        # restarted camera answers. `fail_open_file`: while it exists, opening fails; it hangs
        # instead if the file holds "hang", and reports the camera software missing for "missing".
        if fail_open_file and Path(fail_open_file).exists():
            switch = Path(fail_open_file).read_text().strip()
            if switch == "hang":
                time.sleep(3600)
            if switch == "missing":
                raise ImportError("synthetic camera software missing (test switch)")
            raise RuntimeError("synthetic camera could not be opened (test switch)")
        self._hang_file = hang_file
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

    def _maybe_hang(self, name: str) -> None:
        if not self._hang_file:
            return
        path = Path(self._hang_file)
        try:
            wanted = path.read_text().strip()
        except OSError:
            return
        if wanted in (name, "*"):
            path.unlink(missing_ok=True)
            time.sleep(3600)

    def capture_array(self) -> np.ndarray:
        self._maybe_hang("capture_array")
        return self._pattern(self._width, self._height, channels=4)

    def capture_preview_array(self) -> np.ndarray:
        self._maybe_hang("capture_preview_array")
        return self._pattern(self._preview_width, self._preview_height, channels=4)

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        self._maybe_hang("capture_full_res")
        # Same key set as Picamera2Backend.capture_full_res (SENSOR_METADATA_FIELDS) — no real
        # optics to report ColourGains/SensorTimestamp from, so those two are fixed placeholders.
        metadata = {
            "SensorTimestamp": 0,
            "ExposureTime": self._controls["ExposureTime"],
            "AnalogueGain": self._controls["AnalogueGain"],
            "ColourGains": (1.0, 1.0),
            "LensPosition": self._lens_position,
        }
        return self._pattern(self._width, self._height, channels=3), metadata

    def set_lens_position(self, value: float) -> None:
        self._maybe_hang("set_lens_position")
        self._lens_position = value

    def get_lens_position(self) -> float:
        self._maybe_hang("get_lens_position")
        return self._lens_position

    def autofocus(self) -> tuple[bool, float]:
        self._maybe_hang("autofocus")
        self._lens_position = SIMULATED_AUTOFOCUS_POSITION
        return True, self._lens_position

    def available_controls(self) -> dict[str, tuple]:
        return dict(SYNTHETIC_CONTROL_RANGES)

    def get_controls(self) -> dict:
        self._maybe_hang("get_controls")
        return {**self._controls, "LensPosition": self._lens_position}

    def set_control(self, name: str, value: object) -> None:
        self._maybe_hang("set_control")
        if name in _AE_DEPENDENT_CONTROLS and self._controls.get("AeEnable"):
            # Mirrors Picamera2Backend.set_control's guard so this invariant is testable
            # without hardware — see its docstring for why.
            return
        if name == "LensPosition":
            self._lens_position = value
        else:
            self._controls[name] = value

    @staticmethod
    def _pattern(width: int, height: int, channels: int) -> np.ndarray:
        """Same channel count as Picamera2Backend: the video streams (`main`, `lores`) are
        "XBGR8888", 4 channels with R,G,B first, and the full-resolution still is 3 channels
        (see Picamera2Backend._open and capture_full_res). The padding channel is set to 255,
        not 0, so a consumer that reads it by mistake gets a visibly wrong result in tests.
        """
        frame = np.zeros((height, width, channels), dtype=np.uint8)
        frame[:, :, 1] = 180
        if channels == 4:
            frame[:, :, 3] = 255
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

        self._new_picamera2 = Picamera2
        # The last lens position this app set, applied whenever the camera is opened.
        self._lens_position = DEFAULT_LENS_POSITION
        # Set by a full-res capture: the camera now ignores lens writes until it is reopened
        # (prepare_lens).
        self._lens_ignores_writes = False
        self._open()
        # AwbEnable/AeEnable are write-only in practice: checked directly (not assumed):
        # capture_metadata() reports None for both, unlike ExposureTime/AnalogueGain/
        # LensPosition, which it reports correctly. Cache the last value we set instead.
        probed = self._picam2.camera_controls
        self._control_cache = {
            name: (True if probed[name][2] is None else probed[name][2])
            for name in _CACHED_CONTROLS
            if name in probed
        }
        # The last manual ExposureTime/AnalogueGain set (see set_control).
        self._manual_cache: dict[str, object] = {}

    def _open(self) -> None:
        """Open the camera in the video configuration, in manual focus at the app's lens
        position, and start it."""
        self._picam2 = self._new_picamera2()
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
        self._picam2.set_controls({"AfMode": 0, "LensPosition": self._lens_position})
        self._picam2.start()

    def capture_array(self) -> np.ndarray:
        return self._picam2.capture_array("main")

    def capture_preview_array(self) -> np.ndarray:
        return self._picam2.capture_array("lores")

    def capture_full_res(self) -> tuple[np.ndarray, dict]:
        # No explicit format here either, for the same reason as `main` above -- unconstrained,
        # this negotiates plain 3-channel (logged as "BGR888", genuinely R,G,B as delivered)
        # and comes out correct against a known-color reference; explicitly keying "format"
        # does not, regardless of which string is named.
        # Manual focus at the app's lens position goes into the still configuration itself:
        # configure() otherwise drops AfMode and LensPosition.
        focus = {"AfMode": 0, "LensPosition": self._lens_position}
        still_config = self._picam2.create_still_configuration(controls=dict(focus))
        self._picam2.stop()
        self._picam2.configure(still_config)
        self._picam2.start()
        try:
            array = self._picam2.capture_array("main")
            metadata = self._picam2.capture_metadata()
        finally:
            # Switched back to the video configuration, not reopened, and the lens is not moved.
            # Measured on the rig 2026-10-06 (TODO.md, "Lens stops responding after a full-res
            # capture"): after this switch the camera accepts every lens write and moves on none,
            # but the lens stays where it was (reported position and sharpness unchanged). During
            # an experiment nothing moves the lens (TODO.md, "Plan: nothing moves the lens during
            # an experiment"), so a photo leaves it alone; a later lens command reopens the
            # camera first (prepare_lens), which clears it.
            self._picam2.stop()
            self._picam2.configure(self._video_config)
            self._picam2.start()
            self._picam2.set_controls(dict(focus))
            self._lens_ignores_writes = True
            self._restore_cached_controls()
        sensor_metadata = {key: metadata.get(key) for key in SENSOR_METADATA_FIELDS}
        return array, sensor_metadata

    def prepare_lens(self) -> None:
        """Reopen the camera if a full-res capture has left it ignoring lens writes. Measured
        2026-10-06: closing and reopening in the same process makes the lens follow again (a new
        position reported in 0.6 s); it opens at the last position this app set."""
        if self._lens_ignores_writes:
            self.reset()

    def reset(self) -> None:
        """Close and reopen the camera in the same process: the lens control restarts with it, and
        the camera opens at the last lens position this app set. About 1 s; the app, its settings
        and the focus lock are untouched (Aaron, 2026-10-06: no one at the rig should need to
        restart the app)."""
        self._picam2.stop()
        self._picam2.close()
        self._open()
        self._lens_ignores_writes = False
        self._restore_cached_controls()

    def _restore_cached_controls(self) -> None:
        # configure() and a fresh camera both drop AeEnable/AwbEnable back to the tuning-file
        # defaults, while this app's own cache still claims what they were set to, so the image
        # could go stuck/washed-out without the checkbox ever changing. Restore whatever this app
        # last believed they were, via set_control, not a raw set_controls call, so re-enabling AE
        # here also releases the ExposureTimeMode/AnalogueGainMode manual latch the same way a
        # live checkbox toggle does (see set_control below). A manually-set
        # ExposureTime/AnalogueGain while AE was off is restored after them, from _manual_cache.
        for name, value in dict(self._control_cache).items():
            self.set_control(name, value)
        # Then the manual values, which set_control applies only while AE is off.
        for name, value in dict(self._manual_cache).items():
            self.set_control(name, value)

    def set_lens_position(self, value: float) -> None:
        self._picam2.set_controls({"AfMode": 0, "LensPosition": value})
        self._lens_position = value

    def get_lens_position(self) -> float:
        metadata = self._picam2.capture_metadata()
        return float(metadata.get("LensPosition", DEFAULT_LENS_POSITION))

    def autofocus(self) -> tuple[bool, float]:
        started = time.monotonic()
        step = "did not finish"
        try:
            success = self._picam2.autofocus_cycle(
                wait=AUTOFOCUS_TIMEOUT_S - AUTOFOCUS_METADATA_TIMEOUT_S
            )
            logger.info("autofocus cycle took %.1f s", time.monotonic() - started)
            step = "finished but the camera did not report the lens position"
            metadata = self._picam2.capture_metadata(wait=AUTOFOCUS_METADATA_TIMEOUT_S)
        except FutureTimeoutError:
            # The stuck job stays at the head of picamera2's queue and would block every later
            # call, so cancel it. Nothing else is queued: the caller holds _call_lock. No
            # metadata read here, it could wait just as long. Cancel the latched AF trigger
            # (AfTrigger 1 = Cancel) and go back to manual at the last position the rig set;
            # that write is not confirmed, so the manager clears the lock and the operator locks
            # again, which drives the lens the one consistent way.
            self._picam2.cancel_all_and_flush()
            self._picam2.set_controls(
                {"AfTrigger": 1, "AfMode": 0, "LensPosition": self._lens_position}
            )
            elapsed = time.monotonic() - started
            logger.warning("autofocus %s after %.1f s", step, elapsed)
            raise AutofocusTimeoutError(self._lens_position, step, elapsed) from None
        lens_position = float(metadata.get("LensPosition", DEFAULT_LENS_POSITION))
        # autofocus_cycle leaves AfMode in Auto; the rig always runs manual so a fixed
        # focus can't drift or hunt mid-experiment (see PLAN.md M1/M2).
        self._picam2.set_controls({"AfMode": 0})
        self._lens_position = lens_position
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
        if name == "LensPosition":
            # Through set_lens_position, so the position re-applied after every full-res capture
            # is this one: the startup replay of persisted settings comes in here, and before
            # 2026-10-01 left the remembered position at the 1.0 default.
            self.set_lens_position(float(value))
            return
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
        if name in _AE_DEPENDENT_CONTROLS:
            # Kept so a reopen (prepare_lens, reset) or a full-res capture restores it too: since
            # 2026-10-06 the camera is reopened before lens commands, and a manual exposure falling
            # back to the camera default would change the photos unnoticed (code review).
            self._manual_cache[name] = value
        if name == "AeEnable" and value:
            # picamera2 latches ExposureTimeMode/AnalogueGainMode to manual the moment any
            # nonzero ExposureTime/AnalogueGain is sent (request.py's CompletedRequest.release),
            # and AeEnable alone does not clear that — confirmed against the installed picamera2
            # source. 0 is picamera2's own sentinel for "return to auto," not a real exposure
            # value (no range validation rejects it), so this releases the latch outright.
            self._picam2.set_controls({"ExposureTime": 0, "AnalogueGain": 0})


def lens_check(reported: float | None, locked: float | None) -> dict:
    """Whether a photo was taken at the locked lens position, for its sidecar.

    `reported` is the LensPosition in the photo's own metadata, `locked` the focus lock (None when
    not locked). The photo is flagged when focus is not locked, when the camera reported no
    position, or when the two differ by more than LENS_REPORT_TOLERANCE. Limit: a camera that
    ignores lens writes reports the old position, so this catches a lens the camera reports
    elsewhere (after a reopen or restart), not a lens that moved while the report did not.
    """
    if locked is None:
        reason = "focus not locked"
    elif reported is None:
        reason = "the camera reported no lens position"
    elif abs(reported - locked) > LENS_REPORT_TOLERANCE:
        reason = f"lens reported at {reported:.3f}, locked at {locked:.3f}"
    else:
        reason = None
    return {"reported": reported, "locked": locked, "flagged": reason is not None, "reason": reason}


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
    """The real camera, in its own program (camera_process.py, #51). Falls back to the synthetic
    camera only when the camera software (picamera2) is not installed. A camera that is installed
    but does not open is a fault the status line shows, never a silent switch to synthetic frames
    that would be saved as if they were photos."""
    if os.environ.get("NPEC_RIG_SYNTHETIC_CAMERA"):
        return SyntheticBackend()
    from npec_rig.camera_process import ProcessBackend

    try:
        return ProcessBackend("picamera2")
    except ImportError as exc:
        logger.warning("No camera software installed (%s); using synthetic backend", exc)
        return SyntheticBackend()


class AutofocusTimeoutError(RuntimeError):
    """An autofocus cycle did not finish in time. The backend has already cancelled it and put the
    camera back in manual focus at `lens_position`, the position before the cycle."""

    def __init__(self, lens_position: float, step: str, elapsed_s: float) -> None:
        # Measured 2026-10-06: after a full-res capture left the lens not following commands,
        # autofocus timed out with the lens unchanged (TODO.md, "Lens stops responding").
        super().__init__(f"{LENS_NOT_RESPONDING} (autofocus {step} after {elapsed_s:.0f} s)")
        self.lens_position = lens_position
        self.step = step
        self.elapsed_s = elapsed_s

    def __reduce__(self):
        # Rebuilt from its own fields, not from `args`, so it survives the trip back from the
        # camera program (camera_process.py) with `lens_position` intact.
        return (type(self), (self.lens_position, self.step, self.elapsed_s))


LENS_NOT_RESPONDING = "Lens not responding: press Reset camera"


class LensNotSettledError(RuntimeError):
    """The camera did not report the lens at its target in time: the lens is not following
    commands. Seen 2026-10-05 and 10-06 after a full-res capture: every write is accepted and none
    moves the lens, until the app restarts (TODO.md, "Lens stops responding")."""

    def __init__(self, target: float, reported: float, timeout_s: float) -> None:
        super().__init__(
            f"{LENS_NOT_RESPONDING} (set to {target:.2f}, the camera still reports "
            f"{reported:.2f} after {timeout_s:.0f} s)"
        )
        self.target = target
        self.reported = reported


class FocusLockedError(RuntimeError):
    """A lens move or autofocus was asked for while focus is locked. Aaron, 2026-10-06: a locked
    focus must not be changeable by anyone at the rig until it is unlocked."""

    def __init__(self) -> None:
        super().__init__("Focus is locked: press Unlock focus to change it")


class LensMovedDuringLockError(RuntimeError):
    """The lens was moved by something else while Lock focus was waiting for it."""

    def __init__(self, target: float, moved_to: float | None) -> None:
        where = f" to {moved_to:.2f}" if moved_to is not None else ""
        super().__init__(f"the lens was moved{where} while focus was being locked at {target:.2f}")


# The startup restore waits less than an operator's Lock focus: it runs while the camera is first
# opened, and every camera request waits for it.
LENS_STARTUP_TIMEOUT_S = 10.0


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
        # The last position this app set: what the lens is driven back to when focus is locked.
        # Not the camera's report, which can lag a move by about 45 s after a full-res capture.
        self._commanded_lens_position: float | None = None
        self._drive_lock = Lock()
        self._peaking_enabled = False
        # A camera event row (health.py) records the focus lock at the time.
        from npec_rig import health

        health.set_lens_lock_provider(lambda: self._locked_lens_position)
        # The camera program (camera_process.py) calls this back after it restarted the camera.
        set_listener = getattr(backend, "set_restart_listener", None)
        if set_listener is not None:
            set_listener(self._recover_after_restart)
        try:
            self._apply_persisted_settings()
        except CameraFaultError as exc:
            # The camera did not open; it is retried, and _recover_after_restart replays these
            # settings once it does.
            logger.warning("Settings not applied at startup: %s", exc)

    def _recover_after_restart(self) -> None:
        """After the camera program was restarted (#51): the new camera opens with default
        settings and the lens at the default position, so restore everything the way an app start
        does: settings in order, the lens driven the one consistent way, and the lock kept only if
        the camera confirms the lens where it was locked. Runs on its own thread, after the failed
        call released the camera lock. The lock is cleared in memory only, so the saved
        confirmation can restore it."""
        self._locked_lens_position = None
        try:
            self._apply_persisted_settings()
        except (CameraFaultError, LensMovedDuringLockError) as exc:
            logger.warning("Settings not restored after the camera restart: %s", exc)
            return
        logger.info("camera restored after restart: %s", self.focus_status())

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
            if name in available and name != "LensPosition":
                self._backend.set_control(name, persisted[name])
        # The lens goes back through the one drive path, confirmed, rather than a raw write: a
        # restored lock is only trusted once the camera reports the lens where it was locked.
        if "LensPosition" in persisted and "LensPosition" in available:
            try:
                self._drive_lens(float(persisted["LensPosition"]), LENS_STARTUP_TIMEOUT_S)
            except LensNotSettledError as exc:
                logger.warning("Lens not restored at startup: %s", exc)
                return
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

    def _reset_camera_connection(self) -> None:
        with self._call_lock:
            self._backend.reset()

    def _drive_lens(
        self, value: float, timeout_s: float | None = None, retry: bool = True
    ) -> float:
        """Move the lens to `value` the one consistent way (see LENS_APPROACH_OFFSET) and wait
        until the camera reports it there. Returns the reported position. If the camera does not
        report it, the camera is reset (closed and reopened) and the drive tried once more, unless
        `retry` is False; raises LensNotSettledError if that fails too, and
        LensMovedDuringLockError if another lens command takes over while it waits. Does not touch
        the focus lock: callers decide what a confirmed move means."""
        try:
            return self._drive_lens_once(value, timeout_s)
        except LensNotSettledError as exc:
            if not retry:
                raise
            logger.warning("%s; resetting the camera and trying once more", exc)
        self._reset_camera_connection()
        return self._drive_lens_once(value, timeout_s)

    def _drive_lens_once(self, value: float, timeout_s: float | None = None) -> float:
        """One drive, as `_drive_lens` describes, without the retry. One drive at a time: a second
        one (Lock focus pressed twice) waits for the first."""
        timeout_s = LENS_SETTLE_TIMEOUT_S if timeout_s is None else timeout_s
        with self._drive_lock:
            low = self._backend.available_controls().get("LensPosition", (0.0,))[0]
            approach = max(low, value - LENS_APPROACH_OFFSET)
            self._commanded_lens_position = value
            save_setting("LensPosition", value)
            with self._call_lock:
                self._backend.prepare_lens()
                self._backend.set_lens_position(approach)
            # Timed from here: waiting for the camera lock (a full-res capture) and the reopen in
            # prepare_lens are not the lens being slow.
            approach_sent = time.monotonic()
            # The camera must report the approach position before the target counts: a stuck
            # lens keeps reporting where it was, which can be the target itself (measured
            # 2026-10-06: Lock focus "confirmed" 6.27 that way). Only a target at the bottom of
            # the range, where the approach is the target, cannot be checked like this.
            self._wait_for_report(approach, value, approach_sent + timeout_s, timeout_s)
            # The fixed pause stays as it was, whatever the report does: the sequence the lens
            # moves through is what the validation bands were measured with.
            time.sleep(max(0.0, approach_sent + LENS_APPROACH_PAUSE_S - time.monotonic()))
            if self._commanded_lens_position != value:
                raise LensMovedDuringLockError(value, self._commanded_lens_position)
            with self._call_lock:
                self._backend.set_lens_position(value)
            return self._wait_for_report(value, value, time.monotonic() + timeout_s, timeout_s)

    def _wait_for_report(
        self, position: float, commanded: float, deadline: float, timeout_s: float
    ) -> float:
        """Poll until the camera reports `position`. Raises LensNotSettledError at `deadline`, and
        LensMovedDuringLockError if a newer lens command replaces `commanded` meanwhile."""
        while True:
            reported = self.get_lens_position()
            if self._commanded_lens_position != commanded:
                raise LensMovedDuringLockError(commanded, self._commanded_lens_position)
            if abs(reported - position) <= LENS_REPORT_TOLERANCE:
                return reported
            if time.monotonic() >= deadline:
                raise LensNotSettledError(position, reported, timeout_s)
            time.sleep(LENS_POLL_INTERVAL_S)

    def set_lens_position(self, value: float) -> None:
        """Move the lens directly (the slider), then wait until the camera reports it there. If it
        does not within LENS_SETTLE_TIMEOUT_S, the camera is reset (closed and reopened) and the
        move tried once more; raises LensNotSettledError if that fails too. A newer move arriving
        meanwhile (the slider still being dragged) ends the wait without an error: that move does
        its own check. Raises FocusLockedError, moving nothing, while focus is locked."""
        if self._locked_lens_position is not None:
            raise FocusLockedError()
        for attempt in (1, 2):
            if attempt == 2:
                if self._commanded_lens_position != value:
                    return  # a newer move took over; it does its own check
                self._reset_camera_connection()
            with self._call_lock:
                self._backend.prepare_lens()
                self._commanded_lens_position = value
                self._backend.set_lens_position(value)
            if attempt == 1:
                save_setting("LensPosition", value)
                # The lens moved: a lock set in the moment since the check above is void.
                self._void_lock()
            # A move to where the camera already reports the lens passes at once, stuck or not:
            # the lens is then where it was asked to be.
            try:
                self._wait_for_report(
                    value, value, time.monotonic() + LENS_SETTLE_TIMEOUT_S, LENS_SETTLE_TIMEOUT_S
                )
                return
            except LensMovedDuringLockError:
                return
            except LensNotSettledError as exc:
                if attempt == 2:
                    raise
                logger.warning("%s; resetting the camera and trying once more", exc)

    def get_lens_position(self) -> float:
        with self._call_lock:
            return self._backend.get_lens_position()

    def autofocus(self) -> dict:
        """One autofocus cycle. Raises FocusLockedError, moving nothing, while focus is locked."""
        if self._locked_lens_position is not None:
            raise FocusLockedError()
        timed_out = None
        with self._call_lock:
            self._backend.prepare_lens()
            try:
                success, lens_position = self._backend.autofocus()
            except AutofocusTimeoutError as exc:
                success, lens_position, timed_out = False, exc.lens_position, str(exc)
        save_setting("LensPosition", lens_position)
        self._commanded_lens_position = lens_position
        # The lens moved, or may have: a lock set in the moment since the check above is void.
        self._void_lock()
        return {"success": success, "lens_position": lens_position, "timed_out": timed_out}

    def _void_lock(self) -> None:
        if self._locked_lens_position is not None:
            self._locked_lens_position = None
            save_setting("FocusConfirmed", False)

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
        """Drive the lens to the position last set (the one consistent way, confirmed) and lock
        it there. Raises LensNotSettledError, leaving focus unlocked, if the camera never reports
        it there."""
        # Unlocked first: the lens is about to move, so an older lock must not survive a failure.
        self._locked_lens_position = None
        save_setting("FocusConfirmed", False)
        target = self._commanded_lens_position
        if target is None:
            target = self.get_lens_position()
        self._drive_lens(target)
        if self._commanded_lens_position != target:
            # The lens was moved (slider, autofocus) during the wait: lock nothing.
            raise LensMovedDuringLockError(target, self._commanded_lens_position)
        lens_position = target
        self._locked_lens_position = lens_position
        # Persisted so a restart (dev reload, crash, future systemd restart-on-failure) doesn't
        # silently drop a real confirmation -- see _restore_focus_confirmation for the safety
        # check that only trusts this if the lens is verifiably still where it was confirmed.
        save_setting("FocusConfirmed", True)
        save_setting("FocusConfirmedLensPosition", lens_position)
        return self.focus_status()

    def reset_camera(self) -> dict:
        """The Reset camera button: close and reopen the camera, then drive the lens back to the
        locked position (or the last one set) the one consistent way. The lock stays if the camera
        confirms the position and is cleared if it does not (LensNotSettledError raised). Returns
        the focus status and the position the lens was driven to."""
        self._reset_camera_connection()
        target = self._locked_lens_position
        if target is None:
            target = self._commanded_lens_position
        if target is not None:
            try:
                self._drive_lens(target, retry=False)
            except LensNotSettledError:
                if self._locked_lens_position is not None:
                    self._locked_lens_position = None
                    save_setting("FocusConfirmed", False)
                raise
        return self.focus_status() | {"lens_position_set": target}

    def unlock_focus(self) -> dict:
        self._locked_lens_position = None
        save_setting("FocusConfirmed", False)
        return self.focus_status()

    def focus_status(self) -> dict:
        return {
            "locked": self._locked_lens_position is not None,
            "lens_position": self._locked_lens_position,
        }

    def _capture_full_res(self) -> tuple[np.ndarray, dict]:
        """A full-res photo. Does not move the lens: during an experiment nothing does (TODO.md,
        "Plan: nothing moves the lens during an experiment"). Private: every still is taken by
        `captures.take_photo`, which also saves it with its sidecar (#103)."""
        with self._call_lock:
            return self._backend.capture_full_res()
