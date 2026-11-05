from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


def db_path() -> Path:
    """Path to the SQLite database backing persisted camera settings."""
    return Path(os.environ.get("NPEC_RIG_DB_PATH", "/var/lib/npec-rig/rig.db"))


def _connect() -> sqlite3.Connection:
    """Open the settings DB, creating the parent directory and table if needed."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS camera_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    return conn


def save_setting(name: str, value: object) -> None:
    """Persist one named control value, overwriting any existing value for `name`."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO camera_settings (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, json.dumps(value)),
        )


def load_settings() -> dict:
    """All persisted control values as {name: value}, decoded from JSON. Empty if none saved."""
    with _connect() as conn:
        rows = conn.execute("SELECT name, value FROM camera_settings").fetchall()
    return {name: json.loads(value) for name, value in rows}


# The JPEG setting every full-size photo is saved at (#359). Without a saved one: 85 with full
# colour (Aaron, 2026-11-05), which read plant area 0.4% low against 1.4% at Pillow's own defaults,
# 75 with half colour, that every photo was saved at before #359 (metrology log 26.1).
DEFAULT_PHOTO_QUALITY = {"quality": 85, "chroma": "4:4:4"}


PHOTO_QUALITY_SETTING = "PhotoQuality"  # in camera_settings; not a camera control, so never replayed


def photo_quality() -> dict:
    """The JPEG quality and colour resolution full-size photos are saved at."""
    return {**DEFAULT_PHOTO_QUALITY, **load_settings().get(PHOTO_QUALITY_SETTING, {})}


def set_photo_quality(quality: int, chroma: str) -> dict:
    """Save the JPEG setting for the photos taken from now on, record the change with its time
    (UTC) and return the setting."""
    from datetime import UTC, datetime

    from npec_rig import database  # imported here: database imports this module (db_path)

    save_setting(PHOTO_QUALITY_SETTING, {"quality": quality, "chroma": chroma})
    database.record_photo_quality_change(datetime.now(UTC).isoformat(), quality, chroma)
    return photo_quality()
