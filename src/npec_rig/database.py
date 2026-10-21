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
                validation TEXT,                 -- current validation (validation.photo_check); bands apply unless flagged
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
    (
        5,
        "scheduled capture: a period's photo interval, and every scheduled photo taken or missed",
        (
            # Seconds between scheduled photos, counted from the period's start; NULL for none.
            "ALTER TABLE experiment_period ADD COLUMN interval_s REAL",
            # One row per slot of a schedule, taken or missed. Slot n is due n intervals after the
            # period's start. No reference to capture: a purge deletes the photos, these rows stay
            # as the record of the schedule.
            """
            CREATE TABLE scheduled_photo (
                id INTEGER PRIMARY KEY,
                experiment_id INTEGER NOT NULL REFERENCES experiment (id),
                period_started_at TEXT NOT NULL,  -- UTC, the period this slot belongs to
                slot INTEGER NOT NULL,
                due_at TEXT NOT NULL,             -- UTC, ISO 8601
                capture_id INTEGER,               -- the photo; NULL when missed
                missed_reason TEXT,               -- why it was not taken; NULL when taken
                UNIQUE (experiment_id, period_started_at, slot)
            )
            """,
        ),
    ),
    (
        6,
        "scheduled capture: the interval is part of the experiment and can be changed while it runs",
        (
            "ALTER TABLE experiment ADD COLUMN interval_s REAL",  # seconds; NULL for no schedule
            # UTC. Slot n is due n intervals after this: the latest start, resume or interval change.
            "ALTER TABLE experiment ADD COLUMN schedule_since TEXT",
            "ALTER TABLE scheduled_photo RENAME COLUMN period_started_at TO schedule_since",
            "ALTER TABLE experiment_period DROP COLUMN interval_s",
        ),
    ),
    (
        7,
        "tray readings: every photo read for trays, and one row per tray found in it (#222)",
        (
            # A photo read with no trays found (the dark hours) still has its row here.
            """
            CREATE TABLE tray_read (
                capture_id INTEGER PRIMARY KEY REFERENCES capture (id),
                read_at TEXT NOT NULL,           -- UTC, ISO 8601
                status TEXT NOT NULL             -- read, no tags found, no calibration, no slot layout, placement failed, read failed
            )
            """,
            # Only trays whose tag was found. A tray not found is worked out when shown, from the
            # experiment's earlier photos, never stored (Aaron, 2026-10-21).
            """
            CREATE TABLE tray_reading (
                id INTEGER PRIMARY KEY,
                capture_id INTEGER NOT NULL REFERENCES tray_read (capture_id),
                tray_id INTEGER NOT NULL,        -- the tag ID in cell A1
                slot TEXT NOT NULL,              -- nearest slot of the calibration's layout
                a1_corner TEXT NOT NULL,         -- SW, or NE (turned 180)
                placement TEXT NOT NULL,         -- placed, close call, two trays in one slot
                centre_x_px REAL NOT NULL,       -- tray centre, full-size photo pixels
                centre_y_px REAL NOT NULL,
                tilt_deg REAL NOT NULL,
                margin_mm REAL NOT NULL,
                area_mm2 REAL,                   -- NULL until segmentation (#74)
                UNIQUE (capture_id, tray_id)
            )
            """,
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



# --- Tray readings (#222) ---


def record_tray_readings(capture_id: int, *, read_at: str, status: str, trays: list[dict]) -> None:
    """Save photo `capture_id`'s tray readings, replacing any saved before: a photo read twice
    keeps one row per tray."""
    with _connect() as conn:
        conn.execute("DELETE FROM tray_reading WHERE capture_id = ?", (capture_id,))
        conn.execute(
            "INSERT OR REPLACE INTO tray_read (capture_id, read_at, status) VALUES (?, ?, ?)",
            (capture_id, read_at, status),
        )
        conn.executemany(
            "INSERT INTO tray_reading (capture_id, tray_id, slot, a1_corner, placement,"
            " centre_x_px, centre_y_px, tilt_deg, margin_mm) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (capture_id, t["tray_id"], t["slot"], t["a1_corner"], t["placement"],
                 t["centre_px"][0], t["centre_px"][1], t["tilt_deg"], t["margin_mm"])
                for t in trays
            ],
        )


def tray_readings(capture_id: int) -> dict | None:
    """Photo `capture_id`'s tray readings: when it was read, its status, the trays found in tray
    ID order, and `not_found`: each tray found in an earlier photo of the same experiment but not
    in this one, with the time of the first read photo it was missing from and how many read
    photos it has been missing from, this one included; and `moved`: each tray in another slot
    or turned since the experiment's previous read photo. None when the photo has not been read.

    A removed tray, a swapped tag and a dirty tag all look the same here: the rig cannot tell them
    apart, so each is shown as not found since a time, never guessed at."""
    with _connect() as conn:
        read = conn.execute(
            "SELECT tray_read.*, capture.taken_at, capture.experiment_id FROM tray_read"
            " JOIN capture ON capture.id = tray_read.capture_id WHERE capture_id = ?",
            (capture_id,),
        ).fetchone()
        if read is None:
            return None
        rows = conn.execute(
            "SELECT * FROM tray_reading WHERE capture_id = ? ORDER BY tray_id", (capture_id,)
        ).fetchall()
        not_found, moved = [], []
        if read["experiment_id"] is not None and read["status"] == "read":
            # Photos read with trays placed only: one not read, too dark to find any tag, or with
            # no calibration says nothing about which trays are in it.
            in_experiment = (
                "FROM tray_read JOIN capture ON capture.id = tray_read.capture_id"
                " WHERE tray_read.status = 'read' AND capture.experiment_id = ? AND capture.taken_at <= ?"
            )
            args = (read["experiment_id"], read["taken_at"])
            last_seen = conn.execute(
                "SELECT tray_id, MAX(capture.taken_at) FROM tray_reading"
                " JOIN capture ON capture.id = tray_reading.capture_id"
                " WHERE capture.experiment_id = ? AND capture.taken_at <= ?"
                " AND tray_id NOT IN (SELECT tray_id FROM tray_reading WHERE capture_id = ?)"
                " GROUP BY tray_id ORDER BY tray_id",
                (*args, capture_id),
            ).fetchall()
            for tray_id, seen in last_seen:
                since, photos = conn.execute(
                    f"SELECT MIN(capture.taken_at), COUNT(*) {in_experiment} AND capture.taken_at > ?",
                    (*args, seen),
                ).fetchone()
                not_found.append({"tray_id": tray_id, "since": since, "photos": photos})
            previous = conn.execute(
                f"SELECT capture_id {in_experiment} AND capture.taken_at < ?"
                " ORDER BY capture.taken_at DESC LIMIT 1",
                (*args, read["taken_at"]),
            ).fetchone()
            if previous is not None:
                before = {
                    r["tray_id"]: [r["slot"], r["a1_corner"]]
                    for r in conn.execute("SELECT * FROM tray_reading WHERE capture_id = ?", (previous[0],))
                }
                moved = [
                    {"tray_id": r["tray_id"], "from": before[r["tray_id"]], "to": [r["slot"], r["a1_corner"]]}
                    for r in rows
                    if r["tray_id"] in before and before[r["tray_id"]] != [r["slot"], r["a1_corner"]]
                ]
    trays = [
        {
            "tray_id": r["tray_id"], "slot": r["slot"], "a1_corner": r["a1_corner"],
            "placement": r["placement"], "centre_px": [r["centre_x_px"], r["centre_y_px"]],
            "tilt_deg": r["tilt_deg"], "margin_mm": r["margin_mm"], "area_mm2": r["area_mm2"],
        }
        for r in rows
    ]
    return {"read_at": read["read_at"], "status": read["status"], "trays": trays, "not_found": not_found, "moved": moved}



def unread_photos(limit: int) -> list[str]:
    """Paths of up to `limit` photos taken as captures (not validation, calibration or tripwire
    rounds) that have not been read for trays, newest first: a new photo is read within the
    interval, and photos left from before wait until the reader has nothing newer."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT path FROM capture WHERE purpose = 'capture'"
            " AND id NOT IN (SELECT capture_id FROM tray_read) ORDER BY taken_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [row["path"] for row in rows]

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
    interval_s: float | None = None,
) -> dict:
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO experiment (uuid, name, researcher, tray_height_mm, notes, interval_s,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid, name, researcher, tray_height_mm, notes, interval_s, created_at),
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
# The photo interval can change at any time; a change while running counts slots from then.
_EDITABLE = {
    "set up": {"name", "researcher", "tray_height_mm", "notes", "interval_s"},
    "purged": {"notes"},
}
_EDITABLE_LATER = {"name", "researcher", "notes", "interval_s"}


def update_experiment(experiment_id: int, *, now: str | None = None, **fields: object) -> dict:
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
        if "interval_s" in fields and state == "running":
            if now is None:
                raise ExperimentError("changing the interval while running needs the time")
            conn.execute("UPDATE experiment SET schedule_since = ? WHERE id = ?", (now, experiment_id))
        return _experiment(conn, experiment_id)


def discard_experiment(experiment_id: int) -> None:
    """Remove an experiment that never started: nothing was recorded under it."""
    with _connect() as conn:
        if _experiment(conn, experiment_id)["state"] != "set up":
            raise ExperimentError("only an experiment that has never started can be discarded")
        conn.execute("DELETE FROM experiment WHERE id = ?", (experiment_id,))


def start_experiment(
    experiment_id: int,
    *,
    now: str,
    folder: str | None = None,
    stop_running: bool = False,
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
        conn.execute("UPDATE experiment SET schedule_since = ? WHERE id = ?", (now, experiment_id))
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


# --- Scheduled photos (scheduler.py) ---


def record_scheduled_photos(
    experiment_id: int, schedule_since: str, slots: list[tuple[int, str, int | None, str | None]]
) -> None:
    """Record slots as (slot, due_at, capture_id, missed_reason)."""
    with _connect() as conn:
        conn.executemany(
            "INSERT INTO scheduled_photo (experiment_id, schedule_since, slot, due_at,"
            " capture_id, missed_reason) VALUES (?, ?, ?, ?, ?, ?)",
            [(experiment_id, schedule_since, *slot) for slot in slots],
        )


def schedule_progress(experiment_id: int, schedule_since: str) -> dict:
    """The last slot recorded (0 before the first), photos taken and missed, and when the last
    photo was due."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(slot), 0), COUNT(capture_id), COUNT(missed_reason),"
            " MAX(CASE WHEN capture_id IS NOT NULL THEN due_at END)"
            " FROM scheduled_photo WHERE experiment_id = ? AND schedule_since = ?",
            (experiment_id, schedule_since),
        ).fetchone()
    return {
        "last_slot": row[0],
        "photos_taken": row[1],
        "photos_missed": row[2],
        "last_photo_due_at": row[3],
    }


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
    """Mark a stopped experiment purged, delete its photo rows and their tray readings and mark
    its exports removed, in one transaction. The caller deletes the folder afterwards."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if _experiment(conn, experiment_id)["state"] != "stopped":
            raise ExperimentError("only a stopped experiment can be purged")
        photos = "SELECT id FROM capture WHERE experiment_id = ?"
        conn.execute(f"DELETE FROM tray_reading WHERE capture_id IN ({photos})", (experiment_id,))
        conn.execute(f"DELETE FROM tray_read WHERE capture_id IN ({photos})", (experiment_id,))
        conn.execute("DELETE FROM capture WHERE experiment_id = ?", (experiment_id,))
        conn.execute(
            "UPDATE export SET removed_at = ? WHERE experiment_id = ? AND removed_at IS NULL",
            (now, experiment_id),
        )
        conn.execute("UPDATE experiment SET purged_at = ? WHERE id = ?", (now, experiment_id))
        return _experiment(conn, experiment_id)
