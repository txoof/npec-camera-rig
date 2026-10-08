from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from npec_rig.camera import array_to_jpeg
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
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def _clock_now() -> dict:
    return {
        "boot_id": read_boot_id(),
        "uptime_s": read_uptime_s(),
        "wall": datetime.now(timezone.utc).isoformat(),
    }


def _gap_since(last: dict | None, now: dict) -> dict:
    """How long nothing was recorded before `now`. In the same boot this comes from the kernel's
    uptime and is exact. After a reboot only the wall clock is left, which can be wrong after a
    power cut until the network sets it, so it is recorded for information and flags nothing."""
    if not last:
        return {"same_boot": None, "gap_s": None, "gap_source": None}
    same_boot = last.get("boot_id") is not None and last.get("boot_id") == now["boot_id"]
    if same_boot and last.get("uptime_s") is not None and now["uptime_s"] is not None:
        gap_s = now["uptime_s"] - last["uptime_s"]
        return {"same_boot": True, "gap_s": gap_s, "gap_source": "uptime"}
    try:
        gap_s = (
            datetime.fromisoformat(now["wall"]) - datetime.fromisoformat(last["wall"])
        ).total_seconds()
    except (KeyError, TypeError, ValueError):
        gap_s = None
    return {"same_boot": same_boot, "gap_s": gap_s, "gap_source": "wall clock"}


def record_app_start() -> dict:
    """Called once when the app starts: the gap since the last tick, then a new tick."""
    global _app_start
    now = _clock_now()
    _app_start = {**now, **_gap_since(load_settings().get("LastTick"), now)}
    save_setting("LastTick", now)
    return _app_start


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
        app_up_s = pi_up_s - start["uptime_s"]
    if pi_up_s is None:
        reason = "the Pi uptime could not be read"
    elif pi_up_s < COLD_START_WINDOW_S:
        reason = (
            f"taken {pi_up_s / 60:.0f} min after the Pi started, inside the "
            f"{COLD_START_WINDOW_S / 60:.0f} min cold-start window"
        )
    else:
        reason = None
    save_setting("LastTick", now)
    return {
        "boot_id": now["boot_id"],
        "pi_up_s": pi_up_s,
        "app_up_s": app_up_s,
        "app_start": start,
        "cold_start_window_s": COLD_START_WINDOW_S,
        "flagged": reason is not None,
        "reason": reason,
    }


def captures_root() -> Path:
    """Directory captures are written under, one subdirectory per UTC day."""
    return Path(os.environ.get("NPEC_RIG_CAPTURES_DIR", "/var/lib/npec-rig/captures"))


def save_capture(image: np.ndarray, metadata: dict) -> dict:
    """Write a full-res JPEG plus a JSON sidecar of `metadata`, return the combined record."""
    timestamp = datetime.now(timezone.utc)
    day_dir = captures_root() / timestamp.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)

    stem = timestamp.strftime("%H%M%S_%f")
    jpeg_path = day_dir / f"{stem}.jpg"
    json_path = day_dir / f"{stem}.json"

    jpeg_path.write_bytes(array_to_jpeg(image))
    record = {"timestamp": timestamp.isoformat(), **metadata}
    json_path.write_text(json.dumps(record, indent=2, default=str))

    return {
        "date": timestamp.strftime("%Y-%m-%d"),
        "filename": jpeg_path.name,
        "url": f"/captures/{timestamp.strftime('%Y-%m-%d')}/{jpeg_path.name}",
        **record,
    }


def list_recent_captures(limit: int = 12) -> list[dict]:
    """Most recent captures first, newest day and newest filename within a day sorting first."""
    root = captures_root()
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
                    "url": f"/captures/{day_dir.name}/{jpeg_path.name}",
                    **record,
                }
            )
            if len(entries) >= limit:
                return entries
    return entries
