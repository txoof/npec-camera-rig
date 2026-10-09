"""The rig's current health, one place every part reports into (#51, plan on #82).

The camera program (camera_process.py) reports its state here; the browser's status line and,
later, the fleet health endpoint (#82) read it. In memory, except the last camera fault, which is
saved like the last tick (captures.py) so an app restart does not forget it.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, timezone
from threading import Lock

from npec_rig.settings import load_settings, save_setting

logger = logging.getLogger(__name__)

# The camera states the fleet endpoint will report (#82).
CAMERA_OK = "ok"
CAMERA_RESTARTING = "restarting"
CAMERA_FAILED_TO_REOPEN = "failed_to_reopen"
CAMERA_STATES = (CAMERA_OK, CAMERA_RESTARTING, CAMERA_FAILED_TO_REOPEN)

# A decision, not a measurement (docs/metrology-log.md, section 8): photos taken within this long
# after a camera fault are flagged as not covered by the validation bands. Basis: on 2026-10-06 a
# camera fault left the central trays about half as sharp at the same lens position, and how long
# such a change lasts has not been measured; the same hour as the cold-start window
# (captures.COLD_START_WINDOW_S) until it is.
CAMERA_FAULT_WINDOW_S = 3600.0

_RESTART_COUNT_WINDOW_S = 24 * 3600.0

_lock = Lock()
_camera = {
    "state": CAMERA_OK,
    "detail": None,
    "since": None,
    "reboot_needed": False,
    "last_good_photo": None,
}
_restart_times: list[float] = []


def _wall_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uptime_s() -> float | None:
    try:
        return round(time.clock_gettime(time.CLOCK_BOOTTIME), 2)
    except OSError:
        return None


def _boot_id() -> str | None:
    # Read here, not imported from captures.py, which imports this module.
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except OSError:
        return None


def record_camera_state(state: str, detail: str | None = None, reboot_needed: bool = False) -> None:
    """The camera program's state changed. `detail` says why, in words for the status line."""
    if state not in CAMERA_STATES:
        raise ValueError(f"unknown camera state {state!r}")
    with _lock:
        if state != _camera["state"]:
            _camera["since"] = _wall_now()
        _camera.update(state=state, detail=detail, reboot_needed=reboot_needed)
    log = logger.info if state == CAMERA_OK else logger.warning
    log("camera state %s%s", state, f": {detail}" if detail else "")


def record_camera_fault(reason: str) -> None:
    """The camera stopped responding and its program was ended. Counted, and saved so photos in
    the next CAMERA_FAULT_WINDOW_S are flagged even across an app restart."""
    with _lock:
        now = time.monotonic()
        _restart_times.append(now)
        _restart_times[:] = [t for t in _restart_times if now - t < _RESTART_COUNT_WINDOW_S]
    fault = {"boot_id": _boot_id(), "uptime_s": _uptime_s(), "wall": _wall_now(), "reason": reason}
    try:
        save_setting("LastCameraFault", fault)
    except sqlite3.Error:
        logger.exception("Could not store the camera fault")


def record_good_photo() -> None:
    with _lock:
        _camera["last_good_photo"] = _wall_now()


def _last_fault() -> dict | None:
    try:
        return load_settings().get("LastCameraFault")
    except sqlite3.Error:
        logger.exception("Could not read the last camera fault")
        return None


def camera_fault_check() -> dict:
    """For a photo's sidecar: flagged inside CAMERA_FAULT_WINDOW_S after the last camera fault in
    this boot. A fault before a reboot is not counted here; the cold-start check covers a reboot.
    Limit: only faults the rig detects count, that is a camera call that did not finish in time. A
    camera fault libcamera recovers from by itself, without a call hanging, is not seen."""
    fault = _last_fault()
    reason = None
    since_s = None
    if fault and fault.get("boot_id") is not None and fault.get("boot_id") == _boot_id():
        now = _uptime_s()
        if now is not None and fault.get("uptime_s") is not None:
            since_s = round(now - fault["uptime_s"], 2)
            if since_s < CAMERA_FAULT_WINDOW_S:
                reason = (
                    f"taken {since_s / 60:.0f} min after a camera fault, inside the "
                    f"{CAMERA_FAULT_WINDOW_S / 60:.0f} min camera-fault window"
                )
    return {
        "last_fault": fault,
        "since_fault_s": since_s,
        "camera_fault_window_s": CAMERA_FAULT_WINDOW_S,
        "flagged": reason is not None,
        "reason": reason,
    }


def camera_health() -> dict:
    """The camera part of the rig's health, for the status line and the fleet endpoint (#82)."""
    with _lock:
        now = time.monotonic()
        restarts = sum(1 for t in _restart_times if now - t < _RESTART_COUNT_WINDOW_S)
        snapshot = dict(_camera)
    fault = camera_fault_check()
    return {
        **snapshot,
        "restarts_24h": restarts,
        "last_fault": fault["last_fault"],
        "photos_flagged": fault["flagged"],
        "photos_flagged_reason": fault["reason"],
        "camera_fault_window_s": CAMERA_FAULT_WINDOW_S,
    }


def _reset_for_tests() -> None:
    with _lock:
        _camera.update(
            state=CAMERA_OK, detail=None, since=None, reboot_needed=False, last_good_photo=None
        )
        _restart_times.clear()
