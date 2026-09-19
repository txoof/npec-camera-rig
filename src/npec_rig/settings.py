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
