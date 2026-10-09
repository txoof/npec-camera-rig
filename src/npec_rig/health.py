"""The rig's current health, one place every part reports into (#51, plan on #82).

The camera program (camera_process.py) reports its state here; the browser's status line and,
later, the fleet health endpoint (#82) read it. The current state is in memory. Every camera event
(a fault, a restart, a failed open, a program that cannot be ended) is a row in the
`camera_events` table of rig.db, so the history can be queried and the camera-fault flag and the
24-hour restart count survive an app restart.

Every time stored here is UTC, in columns and keys named `*_utc`, written by `utc_now()` in one
fixed format (always microseconds, always `+00:00`), so sorting the text sorts by time. The
chamber's local time is UTC+2; convert only for display.
"""

from __future__ import annotations

import contextlib
import logging
import socket
import sqlite3
import subprocess
import time
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock

from npec_rig.settings import db_path

logger = logging.getLogger(__name__)

# The camera states the fleet endpoint will report (#82).
CAMERA_OK = "ok"
CAMERA_RESTARTING = "restarting"
CAMERA_FAILED_TO_REOPEN = "failed_to_reopen"
CAMERA_STATES = (CAMERA_OK, CAMERA_RESTARTING, CAMERA_FAILED_TO_REOPEN)

# Kinds of row in camera_events.
EVENT_FAULT = "fault"  # a call did not finish in time, or the program ended during one
EVENT_RESTARTED = "restarted"  # a new camera program is ready after a fault or a failed open
EVENT_OPEN_FAILED = "open_failed"  # a camera program could not open the camera
EVENT_CANNOT_END = "cannot_end"  # a stuck program would not end: the Pi needs a restart
EVENT_KINDS = (EVENT_FAULT, EVENT_RESTARTED, EVENT_OPEN_FAILED, EVENT_CANNOT_END)

# A decision, not a measurement (docs/metrology-log.md, section 8): photos taken within this long
# after a camera fault are flagged as not covered by the validation bands. Basis: on 2026-10-06 a
# camera fault left the central trays about half as sharp at the same lens position, and how long
# such a change lasts has not been measured; the same hour as the cold-start window
# (captures.COLD_START_WINDOW_S) until it is.
CAMERA_FAULT_WINDOW_S = 3600.0

_RESTART_COUNT_WINDOW_S = 24 * 3600.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS camera_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time_utc TEXT NOT NULL,        -- UTC, utc_now() format, e.g. 2026-10-09T08:04:44.736204+00:00
    boot_id TEXT,                  -- Linux boot ID: a new value means the Pi rebooted
    uptime_s REAL,                 -- seconds since the Pi booted (kernel clock, not wall clock)
    kind TEXT NOT NULL,            -- fault, restarted, open_failed, cannot_end
    call TEXT,                     -- the camera call, e.g. capture_full_res
    limit_s REAL,                  -- the time limit that ran out (fault)
    detail TEXT,                   -- the message, in words
    rig TEXT,                      -- the Pi's hostname
    camera TEXT,                   -- camera model and libcamera ID, as the camera program reported
    app_version TEXT,              -- git commit of the running app
    program_pid INTEGER,           -- the camera program this row is about
    lens_locked REAL,              -- focus lock at the time, NULL if not locked
    recovery_s REAL,               -- restarted: seconds from the fault to the new camera ready
    reboot_needed INTEGER NOT NULL DEFAULT 0,
    experiment_id TEXT,            -- NULL until experiments exist (#55)
    purpose TEXT                   -- the photo being taken, if any (capture, validation, ...)
);
CREATE INDEX IF NOT EXISTS camera_events_kind_time ON camera_events (kind, time_utc);
"""

_COLUMNS = (
    "time_utc", "boot_id", "uptime_s", "kind", "call", "limit_s", "detail", "rig", "camera",
    "app_version", "program_pid", "lens_locked", "recovery_s", "reboot_needed", "experiment_id",
    "purpose",
)

_lock = Lock()
_camera = {
    "state": CAMERA_OK,
    "detail": None,
    "since_utc": None,
    "reboot_needed": False,
    "last_good_photo_utc": None,
}

# The purpose of the photo being taken on this thread (captures.take_photo), for a fault row.
_photo_purpose: ContextVar[str | None] = ContextVar("photo_purpose", default=None)
# Set by CameraManager: the focus lock now, for a fault row.
_lens_lock_provider: Callable[[], float | None] | None = None


def utc_now(moment: datetime | None = None) -> str:
    """UTC in the one format stored here: always microseconds, always `+00:00`."""
    moment = moment or datetime.now(timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


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


def _git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(Path(__file__).parent), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


_APP_VERSION = _git_commit()
_RIG = socket.gethostname()


@contextlib.contextmanager
def photo_purpose(purpose: str) -> Iterator[None]:
    """While a photo is taken: a fault in that time records which photo was lost."""
    token = _photo_purpose.set(purpose)
    try:
        yield
    finally:
        _photo_purpose.reset(token)


def set_lens_lock_provider(provider: Callable[[], float | None]) -> None:
    global _lens_lock_provider
    _lens_lock_provider = provider


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.executescript(_SCHEMA)
    return conn


def record_camera_event(
    kind: str,
    *,
    call: str | None = None,
    limit_s: float | None = None,
    detail: str | None = None,
    camera: str | None = None,
    program_pid: int | None = None,
    recovery_s: float | None = None,
    reboot_needed: bool = False,
) -> None:
    """One row in camera_events. A database failure is logged, never raised: the camera's
    recovery must not depend on the record of it."""
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown camera event {kind!r}")
    lens_locked = None
    if _lens_lock_provider is not None:
        try:
            lens_locked = _lens_lock_provider()
        except Exception:
            logger.exception("Could not read the focus lock for a camera event")
    row = {
        "time_utc": utc_now(),
        "boot_id": _boot_id(),
        "uptime_s": _uptime_s(),
        "kind": kind,
        "call": call,
        "limit_s": limit_s,
        "detail": detail,
        "rig": _RIG,
        "camera": camera,
        "app_version": _APP_VERSION,
        "program_pid": program_pid,
        "lens_locked": lens_locked,
        "recovery_s": recovery_s,
        "reboot_needed": int(reboot_needed),
        "experiment_id": None,
        "purpose": _photo_purpose.get(),
    }
    try:
        with contextlib.closing(_connect()) as conn, conn:
            conn.execute(
                f"INSERT INTO camera_events ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
                tuple(row[c] for c in _COLUMNS),
            )
    except sqlite3.Error:
        logger.exception("Could not store the camera event %s", row)


def camera_events(limit: int = 100) -> list[dict]:
    """The latest camera events, newest first."""
    try:
        with contextlib.closing(_connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM camera_events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    except sqlite3.Error:
        logger.exception("Could not read the camera events")
        return []
    return [dict(r) for r in rows]


def record_camera_state(state: str, detail: str | None = None, reboot_needed: bool = False) -> None:
    """The camera program's state changed. `detail` says why, in words for the status line."""
    if state not in CAMERA_STATES:
        raise ValueError(f"unknown camera state {state!r}")
    with _lock:
        if state != _camera["state"]:
            _camera["since_utc"] = utc_now()
        _camera.update(state=state, detail=detail, reboot_needed=reboot_needed)
    log = logger.info if state == CAMERA_OK else logger.warning
    log("camera state %s%s", state, f": {detail}" if detail else "")


def record_good_photo() -> None:
    with _lock:
        _camera["last_good_photo_utc"] = utc_now()


def _last_fault() -> dict | None:
    try:
        with contextlib.closing(_connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM camera_events WHERE kind = ? ORDER BY id DESC LIMIT 1",
                (EVENT_FAULT,),
            ).fetchone()
    except sqlite3.Error:
        logger.exception("Could not read the last camera fault")
        return None
    return dict(row) if row else None


def _faults_since(cutoff_utc: str) -> int:
    try:
        with contextlib.closing(_connect()) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM camera_events WHERE kind = ? AND time_utc >= ?",
                (EVENT_FAULT, cutoff_utc),
            ).fetchone()[0]
    except sqlite3.Error:
        logger.exception("Could not count the camera faults")
        return 0


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
        snapshot = dict(_camera)
    fault = camera_fault_check()
    cutoff = utc_now(datetime.now(timezone.utc) - timedelta(seconds=_RESTART_COUNT_WINDOW_S))
    return {
        **snapshot,
        "restarts_24h": _faults_since(cutoff),
        "last_fault": fault["last_fault"],
        "photos_flagged": fault["flagged"],
        "photos_flagged_reason": fault["reason"],
        "camera_fault_window_s": CAMERA_FAULT_WINDOW_S,
    }


def _reset_for_tests() -> None:
    with _lock:
        _camera.update(
            state=CAMERA_OK,
            detail=None,
            since_utc=None,
            reboot_needed=False,
            last_good_photo_utc=None,
        )
