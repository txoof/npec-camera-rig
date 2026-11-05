from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def db_path() -> Path:
    """Path to the SQLite database backing persisted camera settings."""
    return Path(os.environ.get("NPEC_RIG_DB_PATH", "/var/lib/npec-rig/rig.db"))


CAMERA_SETTINGS_DDL = "CREATE TABLE IF NOT EXISTS camera_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)"


def _connect() -> sqlite3.Connection:
    """Open the settings DB, creating the parent directory and table if needed."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(CAMERA_SETTINGS_DDL)
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


PHOTO_QUALITIES = range(1, 96)  # Pillow advises against more than 95: the file grows, little gained
PHOTO_CHROMAS = ("4:2:0", "4:4:4")  # colour at half resolution both ways, or full


def _saved_photo_quality() -> dict | None:
    """The saved setting, or None when none is saved or it is not one photos can be saved at."""
    saved = load_settings().get(PHOTO_QUALITY_SETTING)
    try:
        if saved["quality"] in PHOTO_QUALITIES and saved["chroma"] in PHOTO_CHROMAS:
            return {"quality": saved["quality"], "chroma": saved["chroma"]}
    except (KeyError, TypeError):
        pass
    return None


def photo_quality() -> dict:
    """The JPEG quality and colour resolution full-size photos are saved at: the saved setting,
    else the default."""
    return _saved_photo_quality() or dict(DEFAULT_PHOTO_QUALITY)


def photo_quality_in_use() -> dict:
    """The setting a photo is about to be saved at. With none saved, or one that photos cannot be
    saved at, the default is saved and recorded as a change: on a rig updated to this version the
    first photo is where the photos switch from 75 with half colour (review of #359)."""
    return _saved_photo_quality() or set_photo_quality(**DEFAULT_PHOTO_QUALITY)


def set_photo_quality(quality: int, chroma: str) -> dict:
    """Save the JPEG setting for the photos taken from now on and record the change with its time
    (UTC), in one transaction; the same setting again is not a change. Returns the setting."""
    from npec_rig import database  # imported here: database imports this module (db_path)

    if quality not in PHOTO_QUALITIES or chroma not in PHOTO_CHROMAS:
        raise ValueError(f"photos cannot be saved at quality {quality!r} with colour {chroma!r}")
    if _saved_photo_quality() != {"quality": quality, "chroma": chroma}:
        database.save_photo_quality(datetime.now(UTC).isoformat(), quality, chroma)
    return photo_quality()
