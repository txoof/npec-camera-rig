"""The experiment's record in `rig.db`: one table per kind of thing (PLAN.md, *Data model and
export*), created and changed only through the numbered migrations below.

The database file's own `user_version` number says how many migrations it has had. On first use
the missing ones are applied in order, each in one transaction with its new number, so a file is
never left half changed and running them again does nothing. A table is added or changed by
appending a migration, never by editing one that has shipped: rigs already have it applied.

The rig's housekeeping tables (`camera_settings`, `capture_analysis`, `derived_image`,
`camera_events`) live in the same file but are created by their own modules and are not touched
here.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from npec_rig.settings import db_path

# (number, what it does, statements). Append only.
MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "capture: one row per photo",
        (
            """
            CREATE TABLE capture (
                id INTEGER PRIMARY KEY,
                taken_at TEXT NOT NULL,          -- UTC, ISO 8601
                path TEXT NOT NULL UNIQUE,       -- YYYY-MM-DD/HHMMSS_ffffff, under the photos folder
                purpose TEXT NOT NULL,           -- capture, validation, calibration, tripwire
                experiment_id INTEGER,           -- NULL until experiments exist (#55)
                calibration TEXT,                -- stem of the calibration active when it was taken
                validation TEXT,                 -- session whose bands apply; NULL until decided
                lens_position REAL,              -- as the camera reported it
                focus_locked_at REAL,            -- the focus lock, NULL when not locked
                exposure_us INTEGER,
                analogue_gain REAL,
                flags TEXT NOT NULL,             -- JSON list of reasons; [] when none
                trust_verdict TEXT               -- NULL until the scheduler's checks exist (M3)
            )
            """,
            "CREATE INDEX capture_taken_at ON capture (taken_at)",
            "CREATE INDEX capture_experiment ON capture (experiment_id, taken_at)",
        ),
    ),
)

SCHEMA_VERSION = MIGRATIONS[-1][0]

_migrated: set[Path] = set()
_migrate_guard = threading.Lock()


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration above the file's `user_version`, return the new version.

    BEGIN IMMEDIATE takes the write lock before the version is read, so two processes starting
    at once cannot both apply the same migration. A file newer than this code is refused rather
    than written to with an older idea of its tables."""
    conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(
                f"rig.db is at schema version {version}, this app knows up to {SCHEMA_VERSION}"
            )
        for number, _description, statements in MIGRATIONS:
            if number <= version:
                continue
            for statement in statements:
                conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {number}")
            version = number
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.isolation_level = ""
    return version


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """A short-lived connection, committed and closed on exit. Migrations run once per file."""
    path = db_path()
    with _migrate_guard:
        if path not in _migrated:
            path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(path, timeout=10)) as conn:
                migrate(conn)
            _migrated.add(path)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_capture(
    *,
    taken_at: str,
    path: str,
    purpose: str,
    calibration: str | None,
    lens_position: float | None,
    focus_locked_at: float | None,
    exposure_us: int | None,
    analogue_gain: float | None,
    flags: list[str],
) -> int:
    """Add one photo's row, return its id."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO capture (taken_at, path, purpose, calibration, lens_position,"
            " focus_locked_at, exposure_us, analogue_gain, flags)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                taken_at,
                path,
                purpose,
                calibration,
                lens_position,
                focus_locked_at,
                exposure_us,
                analogue_gain,
                json.dumps(flags),
            ),
        )
        return cursor.lastrowid


def captures_by_path(paths: list[str]) -> dict[str, dict]:
    """The rows for these photo paths, keyed by path; photos with no row are left out."""
    if not paths:
        return {}
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM capture WHERE path IN ({','.join('?' * len(paths))})", paths
        ).fetchall()
    return {row["path"]: {**dict(row), "flags": json.loads(row["flags"])} for row in rows}
