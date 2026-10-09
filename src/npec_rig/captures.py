from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig import health
from npec_rig.camera import CameraManager, array_to_jpeg, lens_check
from npec_rig.settings import load_settings, save_setting

logger = logging.getLogger(__name__)

# A decision, not a measurement (docs/metrology-log.md): photos taken while the Pi has been up
# less than this are flagged as not covered by the validation bands. Measured 2026-10-06: a cold
# start recovered over about an hour. Stays a placeholder until a cold-start run on SN001.
COLD_START_WINDOW_S = 3600.0

_app_start: dict | None = None


def read_boot_id() -> str | None:
    """Linux's random ID for this boot. A new value means the Pi rebooted since it was stored."""
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def read_uptime_s() -> float | None:
    """Seconds since the Pi booted, from the kernel. Does not depend on the wall clock."""
    try:
        return round(time.clock_gettime(time.CLOCK_BOOTTIME), 2)
    except OSError:
        return None


def _save_tick(now: dict) -> None:
    """Store the last tick. A failure is logged, never raised: a photo already taken is still
    saved, and the app still starts."""
    try:
        save_setting("LastTick", now)
    except sqlite3.Error:
        logger.exception("Could not store the last tick")


def _load_tick() -> dict | None:
    try:
        return load_settings().get("LastTick")
    except sqlite3.Error:
        logger.exception("Could not read the last tick")
        return None


def _clock_now() -> dict:
    return {
        "boot_id": read_boot_id(),
        "uptime_s": read_uptime_s(),
        "wall": datetime.now(timezone.utc).isoformat(),
    }


def _gap_since(last: dict | None, now: dict) -> dict:
    """Time since the last tick before `now`. Ticks are written at app start, at each photo and
    at a clean app stop, so after a crash or power cut this is time since the last photo or
    start, not how long the app was down (a regular tick is #62, M3). In the same boot this
    comes from the kernel's uptime and is exact. After a reboot only the wall clock is left,
    which can be wrong after a power cut until the network sets it, so it is recorded for
    information and flags nothing; a negative wall-clock gap is recorded as unknown."""
    if not last:
        return {"same_boot": None, "gap_s": None, "gap_source": None}
    same_boot = last.get("boot_id") is not None and last.get("boot_id") == now["boot_id"]
    if same_boot and last.get("uptime_s") is not None and now["uptime_s"] is not None:
        gap_s = round(now["uptime_s"] - last["uptime_s"], 2)
        return {"same_boot": True, "gap_s": gap_s, "gap_source": "uptime"}
    try:
        gap_s = (
            datetime.fromisoformat(now["wall"]) - datetime.fromisoformat(last["wall"])
        ).total_seconds()
    except (KeyError, TypeError, ValueError):
        gap_s = None
    if gap_s is not None:
        gap_s = round(gap_s, 2) if gap_s >= 0 else None
    if last.get("boot_id") is None or now["boot_id"] is None:
        same_boot = None
    return {"same_boot": same_boot, "gap_s": gap_s, "gap_source": "wall clock"}


def record_app_start() -> dict:
    """Called once when the app starts: the gap since the last tick, then a new tick."""
    global _app_start
    now = _clock_now()
    _app_start = {**now, **_gap_since(_load_tick(), now)}
    _save_tick(now)
    return _app_start


def record_app_stop() -> None:
    """Called when the app stops cleanly, so the next start measures the time it was down."""
    _save_tick(_clock_now())


def uptime_record() -> dict:
    """Pi and app uptime for a photo's sidecar, flagged inside the cold-start window. Also a tick.

    Flags on Pi uptime alone, so a reboot without a power cut is flagged too: the camera may
    have lost power with the Pi. The gap is recorded so a later measurement can narrow this.
    """
    start = _app_start or record_app_start()
    now = _clock_now()
    pi_up_s = now["uptime_s"]
    app_up_s = None
    if pi_up_s is not None and start["uptime_s"] is not None and now["boot_id"] == start["boot_id"]:
        app_up_s = round(pi_up_s - start["uptime_s"], 2)
    if pi_up_s is None:
        reason = "the Pi uptime could not be read"
    elif pi_up_s < COLD_START_WINDOW_S:
        reason = (
            f"taken {pi_up_s / 60:.0f} min after the Pi started, inside the "
            f"{COLD_START_WINDOW_S / 60:.0f} min cold-start window"
        )
    else:
        reason = None
    _save_tick(now)
    return {
        "boot_id": now["boot_id"],
        "pi_up_s": pi_up_s,
        "app_up_s": app_up_s,
        "app_start": start,
        "cold_start_window_s": COLD_START_WINDOW_S,
        "flagged": reason is not None,
        "reason": reason,
    }


# Every full-resolution still has one of these purposes, recorded in its sidecar.
PURPOSES = ("capture", "validation", "calibration", "tripwire")


def photos_root() -> Path:
    """Directory rig photos are written under, one subdirectory per UTC day. Photos are stored
    by owner, not by purpose (#55): until experiments exist, every photo is a rig photo."""
    return Path(os.environ.get("NPEC_RIG_PHOTOS_DIR", "/var/lib/npec-rig/rig"))


def _photo_dir(timestamp: datetime) -> Path:
    """The one place a photo's folder is picked. An experiment's own folder is added here (#55)."""
    return photos_root() / timestamp.strftime("%Y-%m-%d")


def take_photo(purpose: str, extra: dict | None = None) -> tuple[np.ndarray, dict]:
    """The one way to take a full-resolution still: take it, build its sidecar, save both.

    Every still (Capture, validation round, calibration, tripwire check) comes through here, so
    a check added to the sidecar reaches every photo. `extra` adds caller fields to the sidecar
    (e.g. the validation session). Returns the frame and the saved record; the caller drops the
    frame as soon as it can (a 64MP frame is about 190 MB). CameraBusyError and CameraFaultError
    (the camera stopped responding, camera_process.py) are not caught.
    """
    if purpose not in PURPOSES:
        raise ValueError(f"unknown photo purpose {purpose!r}, expected one of {PURPOSES}")
    manager = CameraManager.instance()
    # Read before the capture, so the lens check compares the photo against the lock it was
    # taken under.
    focus = manager.focus_status()
    with health.photo_purpose(purpose):
        array, sensor_metadata = manager._capture_full_res()
    health.record_good_photo()
    checks = {
        "lens_check": lens_check(sensor_metadata.get("LensPosition"), focus["lens_position"]),
        "uptime": uptime_record(),
        "camera_fault": health.camera_fault_check(),
    }
    sidecar = {
        "purpose": purpose,
        "lens_position": manager.get_lens_position(),
        "roi": manager.get_roi(),
        "focus": focus,
        "sensor_metadata": sensor_metadata,
        **checks,
        # Every reason this photo is not covered by the validation bands, one list for the pages.
        "flags": [check["reason"] for check in checks.values() if check["flagged"]],
        **(extra or {}),
    }
    return array, _save_photo(array, sidecar)


def _save_photo(image: np.ndarray, metadata: dict) -> dict:
    """Write a full-res JPEG plus a JSON sidecar of `metadata`, return the combined record.

    Both are written under temporary names and renamed, sidecar first, so a crash never leaves
    half a file and a JPEG the gallery can see always has its sidecar."""
    timestamp = datetime.now(timezone.utc)
    day_dir = _photo_dir(timestamp)
    day_dir.mkdir(parents=True, exist_ok=True)

    stem = timestamp.strftime("%H%M%S_%f")
    jpeg_path = day_dir / f"{stem}.jpg"
    json_path = day_dir / f"{stem}.json"
    record = {"timestamp": timestamp.isoformat(), **metadata}

    jpeg_tmp = day_dir / f".{stem}.jpg.tmp"
    json_tmp = day_dir / f".{stem}.json.tmp"
    jpeg_tmp.write_bytes(array_to_jpeg(image))
    json_tmp.write_text(json.dumps(record, indent=2, default=str))
    json_tmp.replace(json_path)
    jpeg_tmp.replace(jpeg_path)

    return {
        "date": timestamp.strftime("%Y-%m-%d"),
        "filename": jpeg_path.name,
        "url": f"/photos/{timestamp.strftime('%Y-%m-%d')}/{jpeg_path.name}",
        **record,
    }


def list_recent_captures(limit: int = 12) -> list[dict]:
    """Most recent captures first, newest day and newest filename within a day sorting first."""
    root = photos_root()
    if not root.exists():
        return []

    entries: list[dict] = []
    for day_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        for jpeg_path in sorted(day_dir.glob("*.jpg"), reverse=True):
            json_path = jpeg_path.with_suffix(".json")
            record: dict = {}
            if json_path.exists():
                try:
                    record = json.loads(json_path.read_text())
                except json.JSONDecodeError:
                    logger.warning("Corrupt sidecar JSON, skipping metadata: %s", json_path)
            entries.append(
                {
                    "date": day_dir.name,
                    "filename": jpeg_path.name,
                    "url": f"/photos/{day_dir.name}/{jpeg_path.name}",
                    **record,
                }
            )
            if len(entries) >= limit:
                return entries
    return entries
