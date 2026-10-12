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
                path TEXT NOT NULL UNIQUE,       -- YYYY-MM-DD/HHMMSS_ffffff, under the photos folder (v2: rig/... or experiments/...)
                purpose TEXT NOT NULL,           -- capture, validation, calibration, tripwire
                experiment_id INTEGER,           -- NULL until experiments exist (#55)
                calibration TEXT,                -- stem of the calibration active when it was taken
                validation TEXT,                 -- session whose bands apply (captures.validation_check)
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
    (
        2,
        "experiment and experiment_period; capture paths relative to the data folder",
        (
            """
            CREATE TABLE experiment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,  -- AUTOINCREMENT: a purged id is never reused
                uuid TEXT NOT NULL UNIQUE,
                name TEXT,                       -- the researcher's own text; may be empty
                researcher TEXT,
                tray_height_mm REAL,
                notes TEXT,
                created_at TEXT NOT NULL,        -- UTC, ISO 8601
                folder TEXT UNIQUE               -- experiments/<start date>_<uuid[:8]>, set at first start
            )
            """,
            """
            CREATE TABLE experiment_period (
                id INTEGER PRIMARY KEY,
                experiment_id INTEGER NOT NULL REFERENCES experiment (id),
                started_at TEXT NOT NULL,        -- UTC, ISO 8601
                ended_at TEXT                    -- NULL while running
            )
            """,
            "CREATE INDEX experiment_period_experiment ON experiment_period (experiment_id)",
            # At most one open period in the whole table: only one experiment runs at a time.
            "CREATE UNIQUE INDEX experiment_period_one_running ON experiment_period"
            " ((ended_at IS NULL)) WHERE ended_at IS NULL",
            # Photos from version 1 are all rig photos.
            "UPDATE capture SET path = 'rig/' || path",
        ),
    ),
    (
        3,
        "export: one row per export of an experiment",
        (
            """
            CREATE TABLE export (
                id INTEGER PRIMARY KEY,
                experiment_id INTEGER NOT NULL REFERENCES experiment (id),
                started_at TEXT NOT NULL,        -- UTC, ISO 8601
                finished_at TEXT,                -- NULL while it is being prepared
                file TEXT,                       -- experiments/<folder>/exports/<name>.zip
                bytes INTEGER,
                files INTEGER,                   -- files listed in the manifest
                manifest_sha256 TEXT,            -- checksum of MANIFEST.sha256 itself
                error TEXT                       -- why it failed; NULL when it did not
            )
            """,
            "CREATE INDEX export_experiment ON export (experiment_id)",
        ),
    ),
    (
        4,
        "purge: an experiment's row stays as the record, its exports are marked removed",
        (
            "ALTER TABLE experiment ADD COLUMN purged_at TEXT",  # UTC; NULL unless purged
            "ALTER TABLE export ADD COLUMN removed_at TEXT",  # UTC; the zip was deleted
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
    # Off by default in SQLite, per connection, and only outside a transaction.
    conn.execute("PRAGMA foreign_keys = ON")
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
    experiment_id: int | None = None,
    calibration: str | None,
    validation: str | None,
    lens_position: float | None,
    focus_locked_at: float | None,
    exposure_us: int | None,
    analogue_gain: float | None,
    flags: list[str],
) -> int:
    """Add one photo's row, return its id."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO capture (taken_at, path, purpose, experiment_id, calibration,"
            " validation, lens_position, focus_locked_at, exposure_us, analogue_gain, flags)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                taken_at,
                path,
                purpose,
                experiment_id,
                calibration,
                validation,
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


# --- Experiments ---
# State comes from the periods, never from a stored status: set up (no period), running (newest
# period has no end), stopped (newest period ended). Stop is not final: Resume adds a period, so
# a misunderstood Stop never splits an experiment (Aaron, 2026-10-09).


class ExperimentError(ValueError):
    """An experiment action not allowed in its current state; the message says why."""


def _experiment(conn: sqlite3.Connection, experiment_id: int) -> dict:
    row = conn.execute("SELECT * FROM experiment WHERE id = ?", (experiment_id,)).fetchone()
    if row is None:
        raise LookupError(f"experiment {experiment_id} not found")
    experiment = dict(row)
    experiment["periods"] = [
        dict(p)
        for p in conn.execute(
            "SELECT started_at, ended_at FROM experiment_period WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        )
    ]
    if experiment["purged_at"]:
        experiment["state"] = "purged"
    elif not experiment["periods"]:
        experiment["state"] = "set up"
    elif experiment["periods"][-1]["ended_at"] is None:
        experiment["state"] = "running"
    else:
        experiment["state"] = "stopped"
    return experiment


def create_experiment(
    *,
    uuid: str,
    created_at: str,
    name: str | None = None,
    researcher: str | None = None,
    tray_height_mm: float | None = None,
    notes: str | None = None,
) -> dict:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO experiment (uuid, name, researcher, tray_height_mm, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (uuid, name, researcher, tray_height_mm, notes, created_at),
        )
        return _experiment(conn, cursor.lastrowid)


def get_experiment(experiment_id: int) -> dict:
    with _connect() as conn:
        return _experiment(conn, experiment_id)


def list_experiments() -> list[dict]:
    """Every experiment, newest first."""
    with _connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM experiment ORDER BY id DESC")]
        return [_experiment(conn, i) for i in ids]


def running_experiment() -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT experiment_id FROM experiment_period WHERE ended_at IS NULL"
        ).fetchone()
        return _experiment(conn, row[0]) if row else None


# Name, researcher and notes can be corrected at any time. Tray height can change only before the
# first start: readings already taken depend on it.
_EDITABLE = {"set up": {"name", "researcher", "tray_height_mm", "notes"}, "purged": {"notes"}}
_EDITABLE_LATER = {"name", "researcher", "notes"}


def update_experiment(experiment_id: int, **fields: object) -> dict:
    with _connect() as conn:
        state = _experiment(conn, experiment_id)["state"]
        allowed = _EDITABLE.get(state, _EDITABLE_LATER)
        refused = set(fields) - allowed
        if refused and state == "purged":
            raise ExperimentError("only the notes of a purged experiment can be changed")
        if refused:
            raise ExperimentError(
                f"{', '.join(sorted(refused))} cannot be changed once the experiment has started"
            )
        for column, value in fields.items():
            conn.execute(f"UPDATE experiment SET {column} = ? WHERE id = ?", (value, experiment_id))
        return _experiment(conn, experiment_id)


def discard_experiment(experiment_id: int) -> None:
    """Remove an experiment that never started: nothing was recorded under it."""
    with _connect() as conn:
        if _experiment(conn, experiment_id)["state"] != "set up":
            raise ExperimentError("only an experiment that has never started can be discarded")
        conn.execute("DELETE FROM experiment WHERE id = ?", (experiment_id,))


def start_experiment(
    experiment_id: int, *, now: str, folder: str | None = None, stop_running: bool = False
) -> dict:
    """Start (first time) or resume. `folder` is required on the first start and is the caller's
    to create. With `stop_running`, the running experiment is stopped in the same transaction,
    so there is never a moment with two running or none recorded."""
    with _connect() as conn:
        experiment = _experiment(conn, experiment_id)
        if experiment["state"] == "running":
            raise ExperimentError("this experiment is already running")
        if experiment["state"] == "purged":
            raise ExperimentError("this experiment was purged: its photos are gone")
        running = conn.execute(
            "SELECT experiment_id FROM experiment_period WHERE ended_at IS NULL"
        ).fetchone()
        if running and not stop_running:
            raise ExperimentError("another experiment is running: stop it first")
        if running:
            conn.execute(
                "UPDATE experiment_period SET ended_at = ? WHERE ended_at IS NULL", (now,)
            )
        if experiment["state"] == "set up":
            if folder is None:
                raise ExperimentError("a first start needs a folder")
            conn.execute("UPDATE experiment SET folder = ? WHERE id = ?", (folder, experiment_id))
        conn.execute(
            "INSERT INTO experiment_period (experiment_id, started_at) VALUES (?, ?)",
            (experiment_id, now),
        )
        return _experiment(conn, experiment_id)


def stop_experiment(experiment_id: int, *, now: str) -> dict:
    with _connect() as conn:
        if _experiment(conn, experiment_id)["state"] != "running":
            raise ExperimentError("this experiment is not running")
        conn.execute(
            "UPDATE experiment_period SET ended_at = ? WHERE experiment_id = ? AND ended_at IS NULL",
            (now, experiment_id),
        )
        return _experiment(conn, experiment_id)


# --- Exports ---


def captures_for_experiment(experiment_id: int, until: str | None = None) -> list[dict]:
    """The experiment's photos, oldest first; with `until`, only those taken up to that time."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM capture WHERE experiment_id = ? AND (? IS NULL OR taken_at <= ?)"
            " ORDER BY taken_at",
            (experiment_id, until, until),
        ).fetchall()
    return [dict(row) for row in rows]


def create_export(experiment_id: int, *, now: str) -> dict:
    """A new export, refused for an experiment that has never started, or while an export of it
    is still being prepared. A running experiment can be exported: the export holds its photos
    up to `now` (Aaron, 2026-10-09)."""
    with _connect() as conn:
        # Take the write lock before checking, so two clicks cannot both start one.
        conn.execute("BEGIN IMMEDIATE")
        state = _experiment(conn, experiment_id)["state"]
        if state == "set up":
            raise ExperimentError("an experiment that has not started has nothing to export")
        if state == "purged":
            raise ExperimentError("this experiment was purged: there is nothing left to export")
        busy = conn.execute(
            "SELECT 1 FROM export WHERE experiment_id = ? AND finished_at IS NULL",
            (experiment_id,),
        ).fetchone()
        if busy:
            raise ExperimentError("an export of this experiment is already being prepared")
        cursor = conn.execute(
            "INSERT INTO export (experiment_id, started_at) VALUES (?, ?)", (experiment_id, now)
        )
        return dict(conn.execute("SELECT * FROM export WHERE id = ?", (cursor.lastrowid,)).fetchone())


def finish_export(export_id: int, *, now: str, file: str, bytes: int, files: int, manifest_sha256: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE export SET finished_at = ?, file = ?, bytes = ?, files = ?, manifest_sha256 = ?"
            " WHERE id = ?",
            (now, file, bytes, files, manifest_sha256, export_id),
        )


def fail_export(export_id: int, *, now: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE export SET finished_at = ?, error = ? WHERE id = ?", (now, error, export_id)
        )


def fail_unfinished_exports(*, now: str) -> int:
    """At app start: an export still marked as being prepared was cut off by a restart."""
    with _connect() as conn:
        return conn.execute(
            "UPDATE export SET finished_at = ?, error = 'the app restarted while it was being"
            " prepared' WHERE finished_at IS NULL",
            (now,),
        ).rowcount


def get_export(export_id: int) -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM export WHERE id = ?", (export_id,)).fetchone()
    if row is None:
        raise LookupError(f"export {export_id} not found")
    return dict(row)


def exports_for(experiment_id: int) -> list[dict]:
    """The experiment's exports, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM export WHERE experiment_id = ? ORDER BY id DESC", (experiment_id,)
        ).fetchall()
    return [dict(row) for row in rows]


# --- Purge ---
# PLAN.md, *Purging an experiment*: the one deletion. The experiment's row stays as the record.


def complete_export(experiment_id: int) -> dict | None:
    """The newest export that holds every photo of the experiment: finished, no error, its zip
    not removed, and started after the last photo. A partial export taken while running does not
    count unless no photo came after it."""
    with _connect() as conn:
        last = conn.execute(
            "SELECT MAX(taken_at) FROM capture WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()[0]
        row = conn.execute(
            "SELECT * FROM export WHERE experiment_id = ? AND finished_at IS NOT NULL"
            " AND error IS NULL AND removed_at IS NULL AND (? IS NULL OR started_at >= ?)"
            " ORDER BY id DESC LIMIT 1",
            (experiment_id, last, last),
        ).fetchone()
    return dict(row) if row else None


def purge_experiment(experiment_id: int, *, now: str) -> dict:
    """Mark a stopped experiment purged, delete its photo rows and mark its exports removed, in
    one transaction. The caller deletes the folder afterwards."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if _experiment(conn, experiment_id)["state"] != "stopped":
            raise ExperimentError("only a stopped experiment can be purged")
        conn.execute("DELETE FROM capture WHERE experiment_id = ?", (experiment_id,))
        conn.execute(
            "UPDATE export SET removed_at = ? WHERE experiment_id = ? AND removed_at IS NULL",
            (now, experiment_id),
        )
        conn.execute("UPDATE experiment SET purged_at = ? WHERE id = ?", (now, experiment_id))
        return _experiment(conn, experiment_id)
