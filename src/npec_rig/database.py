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
from collections import Counter
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
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
                status TEXT NOT NULL             -- read, no trays found (no tags found before #331), no calibration, no slot layout, placement failed, read failed
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
    (
        8,
        "tray readings: the segmenter that made each tray's area (#75)",
        ("ALTER TABLE tray_reading ADD COLUMN segmenter TEXT",),  # e.g. "green threshold, 0.1"; NULL with no area
    ),
    (
        9,
        "tray readings: the raw measurement under each area, so another calibration can be applied later (#75)",
        (
            "ALTER TABLE tray_reading ADD COLUMN plant_px INTEGER",  # plant pixels inside the tray outline
            "ALTER TABLE tray_reading ADD COLUMN plant_centre_x_px REAL",  # their centre, full-size photo pixels
            "ALTER TABLE tray_reading ADD COLUMN plant_centre_y_px REAL",
            "ALTER TABLE tray_reading ADD COLUMN calibration TEXT",  # the calibration area_mm2 was worked out with
        ),
    ),
    (
        10,
        "exclusions: why a photo's plant areas are left out, worked out again as photos come (#288)",
        (
            """
            CREATE TABLE exclusion (
                capture_id INTEGER PRIMARY KEY REFERENCES capture (id),
                name TEXT,                       -- lights off, light changing, light disturbed, light off norm; NULL: none
                norm_e REAL,                     -- the norm (exposure us x gain) it was worked out with; NULL until there is one
                limit_fraction REAL,             -- how far from the norm counts as off it, e.g. 0.21
                worked_out_at TEXT NOT NULL      -- UTC, ISO 8601
            )
            """,
        ),
    ),
    (
        11,
        "light warning dismissals: when the researcher dismissed it, and the hours it covered (#288)",
        (
            """
            CREATE TABLE light_warning_dismissal (
                id INTEGER PRIMARY KEY,
                experiment_id INTEGER NOT NULL REFERENCES experiment (id),
                dismissed_at TEXT NOT NULL,      -- UTC, ISO 8601
                covers_until TEXT NOT NULL       -- UTC: the end of the last stretch it covered
            )
            """,
        ),
    ),
    (
        12,
        "each tray's outline past the photo edge, mm (#282)",
        (
            "ALTER TABLE tray_reading ADD COLUMN outside_mm REAL",  # 0 when inside; NULL: read before #282
        ),
    ),
    (
        13,
        "tray readings: two trays in one photo may carry the same tag (#302)",
        # SQLite cannot drop a UNIQUE constraint: the table is copied into one without it.
        (
            """
            CREATE TABLE tray_reading_13 (
                id INTEGER PRIMARY KEY,
                capture_id INTEGER NOT NULL REFERENCES tray_read (capture_id),
                tray_id INTEGER NOT NULL,        -- the tag ID in cell A1; twice in a photo when two trays carry it
                slot TEXT NOT NULL,              -- nearest slot of the calibration's layout
                a1_corner TEXT NOT NULL,         -- SW, or NE (turned 180)
                placement TEXT NOT NULL,         -- placed, close call, two trays in one slot
                centre_x_px REAL NOT NULL,       -- tray centre, full-size photo pixels
                centre_y_px REAL NOT NULL,
                tilt_deg REAL NOT NULL,
                margin_mm REAL NOT NULL,
                area_mm2 REAL,                   -- NULL when not worked out
                segmenter TEXT,                  -- e.g. "green threshold, 0.1"; NULL with no area
                plant_px INTEGER,                -- plant pixels inside the tray outline
                plant_centre_x_px REAL,          -- their centre, full-size photo pixels
                plant_centre_y_px REAL,
                calibration TEXT,                -- the calibration area_mm2 was worked out with
                outside_mm REAL                  -- 0 when inside; NULL: read before #282
            )
            """,
            "INSERT INTO tray_reading_13 (id, capture_id, tray_id, slot, a1_corner, placement,"
            " centre_x_px, centre_y_px, tilt_deg, margin_mm, area_mm2, segmenter, plant_px,"
            " plant_centre_x_px, plant_centre_y_px, calibration, outside_mm)"
            " SELECT id, capture_id, tray_id, slot, a1_corner, placement,"
            " centre_x_px, centre_y_px, tilt_deg, margin_mm, area_mm2, segmenter, plant_px,"
            " plant_centre_x_px, plant_centre_y_px, calibration, outside_mm FROM tray_reading",
            "DROP TABLE tray_reading",
            "ALTER TABLE tray_reading_13 RENAME TO tray_reading",
            "CREATE INDEX tray_reading_capture ON tray_reading (capture_id, tray_id)",
        ),
    ),
    (
        14,
        "tray readings: trays found in the photo, with or without a tag (#331)",
        # NOT NULL cannot be dropped either: copied into a table where what a tray found in the
        # photo may not know is nullable.
        (
            """
            CREATE TABLE tray_reading_14 (
                id INTEGER PRIMARY KEY,
                capture_id INTEGER NOT NULL REFERENCES tray_read (capture_id),
                tray_id INTEGER,                 -- the tag ID inside the outline; NULL: no tag
                slot TEXT,                       -- nearest slot of the calibration's layout; NULL: no layout
                a1_corner TEXT,                  -- SW, or NE (turned 180); placed from the tag only, else NULL
                placement TEXT NOT NULL,         -- placed, close call, two trays in one slot, two tags in one outline
                centre_x_px REAL NOT NULL,       -- tray centre (a tag seen with no tray: the tag's), full-size photo pixels
                centre_y_px REAL NOT NULL,
                tilt_deg REAL NOT NULL,
                margin_mm REAL,                  -- placed from the tag only, else NULL
                area_mm2 REAL,                   -- NULL when not worked out
                segmenter TEXT,                  -- e.g. "green threshold, 0.1"; NULL with no area
                plant_px INTEGER,                -- plant pixels inside the tray outline
                plant_centre_x_px REAL,          -- their centre, full-size photo pixels
                plant_centre_y_px REAL,
                calibration TEXT,                -- the calibration area_mm2 was worked out with
                outside_mm REAL,                 -- 0 when inside; NULL: read before #282
                found TEXT,                      -- photo + tag, photo, no tag, tag only; NULL: read before #331
                warnings TEXT,                   -- JSON list of warning words; NULL: read before #331
                outline TEXT                     -- JSON [[x, y]] x 4, full-size photo pixels; NULL: read before #331
            )
            """,
            "INSERT INTO tray_reading_14 (id, capture_id, tray_id, slot, a1_corner, placement, centre_x_px, centre_y_px, tilt_deg, margin_mm, area_mm2, segmenter, plant_px, plant_centre_x_px, plant_centre_y_px, calibration, outside_mm) SELECT id, capture_id, tray_id, slot, a1_corner, placement, centre_x_px, centre_y_px, tilt_deg, margin_mm, area_mm2, segmenter, plant_px, plant_centre_x_px, plant_centre_y_px, calibration, outside_mm FROM tray_reading",
            "DROP TABLE tray_reading",
            "ALTER TABLE tray_reading_14 RENAME TO tray_reading",
            "CREATE INDEX tray_reading_capture ON tray_reading (capture_id, tray_id)",
        ),
    ),
    (
        15,
        "experiment: how long a tray may stay in one table location (#332)",
        (
            # Hours in a row in one table location before the experiment warns; default 4 days, a decision
            # (Aaron, 2026-10-30).
            "ALTER TABLE experiment ADD COLUMN dwell_limit_h REAL NOT NULL DEFAULT 96",
        ),
    ),
    (
        16,
        "experiment_hidden_tray: trays hidden on an experiment's table locations panel (#332)",
        (
            # A tray hidden gives no warning; its readings stay as they are (Aaron, 2026-11-02).
            """
            CREATE TABLE experiment_hidden_tray (
                experiment_id INTEGER NOT NULL REFERENCES experiment (id),
                tray_id INTEGER NOT NULL,
                hidden_at TEXT NOT NULL,         -- UTC, ISO 8601
                PRIMARY KEY (experiment_id, tray_id)
            )
            """,
        ),
    ),
    (
        17,
        "app starts: when the app came back, to measure downtime (#62)",
        (
            """
            CREATE TABLE app_start (
                id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL         -- UTC, ISO 8601
            )
            """,
        ),
    ),
    (
        18,
        "capture: whether the clock had the network time when the photo was taken (#62)",
        # 1 had it, 0 had not (the photo's time may be wrong), NULL taken before this version.
        ("ALTER TABLE capture ADD COLUMN clock_synced INTEGER",),
    ),
    (
        19,
        "tray_layout: suggested tray layouts and the checks against them, per experiment (#343)",
        (
            # Saved with the experiment (Aaron, 2026-11-02). A suggestion keeps, per tray, where it
            # lay before (read from `capture_id`) and which rows and columns were then on an
            # outside edge, so every round's edge history is kept. A check keeps its photo.
            """
            CREATE TABLE tray_layout (
                id INTEGER PRIMARY KEY,
                experiment_id INTEGER NOT NULL REFERENCES experiment (id),
                kind TEXT NOT NULL,              -- 'suggestion', 'check' or 'cancel'
                made_at TEXT NOT NULL,           -- UTC, ISO 8601
                capture_id INTEGER,              -- the photo read; no reference: a purge deletes it
                suggestion_id INTEGER REFERENCES tray_layout (id),  -- a check: what it compared with
                details TEXT NOT NULL            -- JSON: the trays, and the seed of a suggestion
            )
            """,
            "CREATE INDEX tray_layout_experiment ON tray_layout (experiment_id, kind, id)",
        ),
    ),
    (
        20,
        "capture: the JPEG quality and colour resolution the photo was saved at; every change of"
        " the setting (#359)",
        # NULL for photos taken before this version: they were all saved at 75 with "4:2:0"
        # (Pillow's defaults, metrology log 26).
        (
            "ALTER TABLE capture ADD COLUMN jpeg_quality INTEGER",
            "ALTER TABLE capture ADD COLUMN jpeg_chroma TEXT",  # "4:2:0" or "4:4:4"
            """
            CREATE TABLE photo_quality_change (
                id INTEGER PRIMARY KEY,
                changed_at TEXT NOT NULL,        -- UTC, ISO 8601
                quality INTEGER NOT NULL,        -- JPEG quality, 1 to 95
                chroma TEXT NOT NULL             -- "4:2:0" or "4:4:4"
            )
            """,
        ),
    ),
    (
        21,
        "cell_reading: the plant of each cell of each tray in a photo; tray_reading: where a 2 x 2"
        " tray's cell A1 lies from its tag (#364)",
        (
            # Degrees clockwise from the tag's top to cell A1, from the tray's first photo in the
            # experiment; NULL for every other tray type (tray_placement.a1_bearing_deg).
            "ALTER TABLE tray_reading ADD COLUMN a1_bearing_deg REAL",
            """
            CREATE TABLE cell_reading (
                id INTEGER PRIMARY KEY,
                capture_id INTEGER NOT NULL REFERENCES capture (id),
                tray_id INTEGER NOT NULL,
                cell TEXT NOT NULL,              -- "B3"
                holds TEXT NOT NULL,             -- "plant", or "tag": the tray tag's cell
                centre_x_px REAL NOT NULL,       -- full-size photo pixels
                centre_y_px REAL NOT NULL,
                corners TEXT NOT NULL,           -- JSON, the four corners of the cell's opening
                plant_px INTEGER,                -- NULL: the photo could not be segmented
                area_mm2 REAL,
                plant_centre_x_px REAL,
                plant_centre_y_px REAL,
                over_other_cells INTEGER,        -- 1: a piece counted here covers another cell, or the reverse
                segmenter TEXT,                  -- what made the mask, as tray_reading.segmenter
                cell_rule TEXT                   -- how plant pieces were given to cells (tray_readings.CELL_RULE)
            )
            """,
            "CREATE INDEX cell_reading_capture ON cell_reading (capture_id, tray_id)",
        ),
    ),
)

SCHEMA_VERSION = MIGRATIONS[-1][0]

# How long after the last read photo that had it a tray missing from a photo is still reported as
# not seen. After that it was taken away on purpose, not lost; it is reported again if it comes
# back and goes missing once more. A decision, not a measurement (Aaron, 2026-10-30).
NOT_SEEN_FOR = timedelta(hours=48)

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
    clock_synced: bool | None = None,
    jpeg_quality: int | None = None,
    jpeg_chroma: str | None = None,
) -> int:
    """Add one photo's row, return its id."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO capture (taken_at, path, purpose, experiment_id, calibration,"
            " validation, lens_position, focus_locked_at, exposure_us, analogue_gain, flags,"
            " clock_synced, jpeg_quality, jpeg_chroma) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                None if clock_synced is None else int(clock_synced),
                jpeg_quality,
                jpeg_chroma,
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
        conn.execute("DELETE FROM cell_reading WHERE capture_id = ?", (capture_id,))
        conn.execute(
            "INSERT OR REPLACE INTO tray_read (capture_id, read_at, status) VALUES (?, ?, ?)",
            (capture_id, read_at, status),
        )
        conn.executemany(
            "INSERT INTO tray_reading (capture_id, tray_id, slot, a1_corner, placement,"
            " centre_x_px, centre_y_px, tilt_deg, margin_mm, area_mm2, segmenter,"
            " plant_px, plant_centre_x_px, plant_centre_y_px, calibration, outside_mm, found, warnings, outline,"
            " a1_bearing_deg)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (capture_id, t["tray_id"], t["slot"], t["a1_corner"], t["placement"],
                 t["centre_px"][0], t["centre_px"][1], t["tilt_deg"], t["margin_mm"],
                 t.get("area_mm2"), t.get("segmenter"), t.get("plant_px"),
                 *(t.get("plant_centre_px") or (None, None)), t.get("calibration"), t.get("outside_mm"),
                 t.get("found"), _json_or_none(t.get("warnings")), _json_or_none(t.get("outline_px")),
                 t.get("a1_bearing_deg"))
                for t in trays
            ],
        )
        conn.executemany(
            "INSERT INTO cell_reading (capture_id, tray_id, cell, holds, centre_x_px, centre_y_px, corners,"
            " plant_px, area_mm2, plant_centre_x_px, plant_centre_y_px, over_other_cells, segmenter, cell_rule)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (capture_id, t["tray_id"], c["cell"], c["holds"], *c["centre_px"], json.dumps(c["corners_px"]),
                 c.get("plant_px"), c.get("area_mm2"), *(c.get("plant_centre_px") or (None, None)),
                 None if c.get("over_other_cells") is None else int(c["over_other_cells"]),
                 c.get("segmenter"), c.get("cell_rule"))
                for t in trays for c in t.get("cells", [])
            ],
        )


def first_a1_bearing(experiment_id: int | None, tray_id: int, taken_at: str) -> float | None:
    """Where a 2 x 2 tray's cell A1 lay from its tag in its first photo of experiment
    `experiment_id` taken before `taken_at` (tray_reading.a1_bearing_deg, #364); None when there
    is none, or the photo is in no experiment: then that photo is the tray's first."""
    if experiment_id is None:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT tray_reading.a1_bearing_deg FROM tray_reading JOIN capture ON capture.id = tray_reading.capture_id"
            " WHERE capture.experiment_id = ? AND tray_reading.tray_id = ? AND tray_reading.a1_bearing_deg IS NOT NULL"
            " AND capture.taken_at < ? ORDER BY capture.taken_at LIMIT 1",
            (experiment_id, tray_id, taken_at),
        ).fetchone()
    return None if row is None else row[0]


def _json_or_none(value: object) -> str | None:
    return None if value is None else json.dumps(value)


def tray_readings(capture_id: int) -> dict | None:
    """Photo `capture_id`'s tray readings: when it was read, its status, the trays found in tray
    ID order, and `not_found`: each tray found in an earlier photo of the same experiment but not
    in this one, with where it was last found (`seen_in`: that photo's path and calibration and
    the tray's centre, for its table location, `tray_readings.capture_readings`, #332), the
    time of the first read photo it was missing from and how many read photos it has been missing
    from, this one included; and `in_both`: each tray also found in the experiment's previous read
    photo, with its centre in this one and where it was in that one (`before`), for whether it
    left its table location (`moved`, `tray_readings.capture_readings`, #332). None when the photo has not
    been read.

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
        cells: dict[int, list[dict]] = {}
        for c in conn.execute("SELECT * FROM cell_reading WHERE capture_id = ? ORDER BY id", (capture_id,)):
            cells.setdefault(c["tray_id"], []).append({
                "cell": c["cell"], "holds": c["holds"], "centre_px": [c["centre_x_px"], c["centre_y_px"]],
                "corners_px": json.loads(c["corners"]), "plant_px": c["plant_px"], "area_mm2": c["area_mm2"],
                "plant_centre_px": None if c["plant_centre_x_px"] is None else [c["plant_centre_x_px"], c["plant_centre_y_px"]],
                "over_other_cells": None if c["over_other_cells"] is None else bool(c["over_other_cells"]),
                "segmenter": c["segmenter"], "cell_rule": c["cell_rule"],
            })
        not_found, in_both = [], []
        if read["experiment_id"] is not None and read["status"] == "read":
            # Photos read with trays placed only: one not read, too dark to find any tag, or with
            # no calibration says nothing about which trays are in it.
            in_experiment = (
                "FROM tray_read JOIN capture ON capture.id = tray_read.capture_id"
                " WHERE tray_read.status = 'read' AND capture.experiment_id = ? AND capture.taken_at <= ?"
            )
            args = (read["experiment_id"], read["taken_at"])
            # SQLite takes the bare columns from the row holding the MAX: where the tray was
            # last found. A tray with no tag (#331) cannot be followed from photo to photo: left
            # out on both sides.
            last_seen = conn.execute(
                "SELECT tray_id, MAX(capture.taken_at), capture.path, capture.calibration, centre_x_px, centre_y_px"
                " FROM tray_reading"
                " JOIN capture ON capture.id = tray_reading.capture_id"
                " WHERE capture.experiment_id = ? AND capture.taken_at <= ? AND tray_id IS NOT NULL"
                " AND tray_id NOT IN"
                " (SELECT tray_id FROM tray_reading WHERE capture_id = ? AND tray_id IS NOT NULL)"
                " GROUP BY tray_id ORDER BY tray_id",
                (*args, capture_id),
            ).fetchall()
            for tray_id, seen, path, calibration, x, y in last_seen:
                if datetime.fromisoformat(read["taken_at"]) - datetime.fromisoformat(seen) > NOT_SEEN_FOR:
                    continue
                since, photos = conn.execute(
                    f"SELECT MIN(capture.taken_at), COUNT(*) {in_experiment} AND capture.taken_at > ?",
                    (*args, seen),
                ).fetchone()
                not_found.append({
                    "tray_id": tray_id, "since": since, "photos": photos, "last_seen": seen,
                    "seen_in": {"path": path, "calibration": calibration, "centre_px": (x, y)},
                })
            previous = conn.execute(
                f"SELECT capture_id, capture.path, capture.calibration {in_experiment} AND capture.taken_at < ?"
                " ORDER BY capture.taken_at DESC LIMIT 1",
                (*args, read["taken_at"]),
            ).fetchone()
            if previous is not None:
                earlier = conn.execute("SELECT * FROM tray_reading WHERE capture_id = ?", (previous[0],)).fetchall()
                # A tag two trays carry, in either photo, says nothing about which tray moved (#302).
                shared = {t for photo in (earlier, rows) for t, n in Counter(r["tray_id"] for r in photo).items() if n > 1}
                before = {
                    r["tray_id"]: (r["centre_x_px"], r["centre_y_px"])
                    for r in earlier if r["tray_id"] is not None and r["tray_id"] not in shared
                }
                in_both = [
                    {"tray_id": r["tray_id"], "centre_px": (r["centre_x_px"], r["centre_y_px"]),
                     "before": {"path": previous[1], "calibration": previous[2], "centre_px": before[r["tray_id"]]}}
                    for r in rows if r["tray_id"] in before
                ]
    trays = [
        {
            "tray_id": r["tray_id"], "slot": r["slot"], "a1_corner": r["a1_corner"],
            "placement": r["placement"], "centre_px": [r["centre_x_px"], r["centre_y_px"]],
            "tilt_deg": r["tilt_deg"], "margin_mm": r["margin_mm"], "area_mm2": r["area_mm2"],
            "segmenter": r["segmenter"], "plant_px": r["plant_px"],
            "plant_centre_px": None if r["plant_centre_x_px"] is None else [r["plant_centre_x_px"], r["plant_centre_y_px"]],
            "calibration": r["calibration"], "outside_mm": r["outside_mm"], "found": r["found"],
            "warnings": [] if r["warnings"] is None else json.loads(r["warnings"]),
            "outline_px": None if r["outline"] is None else json.loads(r["outline"]),
            "a1_bearing_deg": r["a1_bearing_deg"],
            # Cells are saved only for a tray named by one tag (#364).
            "cells": cells.get(r["tray_id"], []) if r["tray_id"] is not None else [],
        }
        for r in rows
    ]
    return {"read_at": read["read_at"], "status": read["status"], "trays": trays, "not_found": not_found, "in_both": in_both}



def record_exclusions(rows: list[dict], *, worked_out_at: str) -> None:
    """Save each photo's exclusion (`capture_id`, `name`, `norm_e`, `limit_fraction`), replacing
    what was saved before."""
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO exclusion (capture_id, name, norm_e, limit_fraction, worked_out_at)"
            " VALUES (?, ?, ?, ?, ?)",
            [(r["capture_id"], r["name"], r["norm_e"], r["limit_fraction"], worked_out_at) for r in rows],
        )


def exclusion(capture_id: int) -> dict | None:
    """Photo `capture_id`'s saved exclusion row, None when none has been worked out."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM exclusion WHERE capture_id = ?", (capture_id,)).fetchone()
    return dict(row) if row else None


def experiment_exclusions(experiment_id: int) -> list[dict]:
    """The experiment's photos taken as captures, oldest first: `taken_at` and the saved
    exclusion `name` (None for none, or when none has been worked out)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT capture.taken_at, exclusion.name FROM capture"
            " LEFT JOIN exclusion ON exclusion.capture_id = capture.id"
            " WHERE capture.experiment_id = ? AND capture.purpose = 'capture' ORDER BY capture.taken_at",
            (experiment_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def record_light_warning_dismissal(experiment_id: int, *, dismissed_at: str, covers_until: str) -> None:
    """Save a dismissal of the experiment's light warning."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO light_warning_dismissal (experiment_id, dismissed_at, covers_until) VALUES (?, ?, ?)",
            (experiment_id, dismissed_at, covers_until),
        )


def light_warning_dismissals(experiment_id: int) -> list[dict]:
    """The experiment's light warning dismissals, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM light_warning_dismissal WHERE experiment_id = ? ORDER BY dismissed_at",
            (experiment_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def experiment_tray_areas(experiment_id: int) -> dict[int, dict[int, float]]:
    """The saved plant areas of each of the experiment's photos whose trays were read (status
    `read`): tray ID to mm2, by capture id; empty for a read photo with no area. Photos not read,
    or read with another status, are not included. A tag two trays carry in one photo is left
    out of that photo: neither area counts (#302)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT tray_read.capture_id, tray_reading.tray_id, tray_reading.area_mm2 FROM tray_read"
            " JOIN capture ON capture.id = tray_read.capture_id"
            " LEFT JOIN tray_reading ON tray_reading.capture_id = tray_read.capture_id"
            " WHERE capture.experiment_id = ? AND tray_read.status = 'read'",
            (experiment_id,),
        ).fetchall()
    areas: dict[int, dict[int, float]] = {}
    carried: Counter = Counter()
    for capture_id, tray_id, area in rows:
        photo = areas.setdefault(capture_id, {})
        if tray_id is not None:
            carried[capture_id, tray_id] += 1
            if area is not None:
                photo[tray_id] = area
    for (capture_id, tray_id), n in carried.items():
        if n > 1:
            areas[capture_id].pop(tray_id, None)
    return areas


def experiment_tray_positions(experiment_id: int) -> list[dict]:
    """Where each tray was found in each of the experiment's read photos (status `read`), oldest
    first: tray ID, the photo's time, path and calibration, and the tray's centre in full-size
    photo pixels. A tray with no tag cannot be followed from photo to photo and is left out; so is
    a tag two trays carry in one photo, from that photo (#302)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT tray_reading.tray_id, capture.taken_at, capture.path, capture.calibration,"
            " tray_reading.centre_x_px, tray_reading.centre_y_px FROM tray_reading"
            " JOIN tray_read ON tray_read.capture_id = tray_reading.capture_id"
            " JOIN capture ON capture.id = tray_reading.capture_id"
            " WHERE capture.experiment_id = ? AND tray_read.status = 'read' AND tray_reading.tray_id IS NOT NULL"
            " AND (SELECT COUNT(*) FROM tray_reading AS other WHERE other.capture_id = tray_reading.capture_id"
            " AND other.tray_id = tray_reading.tray_id) = 1"
            " ORDER BY capture.taken_at, tray_reading.tray_id",
            (experiment_id,),
        ).fetchall()
    return [
        {"tray_id": r["tray_id"], "taken_at": r["taken_at"], "path": r["path"], "calibration": r["calibration"],
         "centre_px": (r["centre_x_px"], r["centre_y_px"])}
        for r in rows
    ]


def hidden_trays(experiment_id: int) -> set[int]:
    """The tray IDs hidden on the experiment's table locations panel (#332)."""
    with _connect() as conn:
        rows = conn.execute("SELECT tray_id FROM experiment_hidden_tray WHERE experiment_id = ?", (experiment_id,))
        return {r[0] for r in rows.fetchall()}


def hide_tray(experiment_id: int, tray_id: int, *, now: str) -> None:
    """Hide tray `tray_id` on the experiment's panel: it gives no warning until shown again. Its
    readings are unchanged. Hiding a hidden tray keeps its first time."""
    with _connect() as conn:
        _experiment(conn, experiment_id)  # LookupError for no such experiment
        conn.execute(
            "INSERT OR IGNORE INTO experiment_hidden_tray (experiment_id, tray_id, hidden_at) VALUES (?, ?, ?)",
            (experiment_id, tray_id, now),
        )


def show_tray(experiment_id: int, tray_id: int) -> None:
    """Show a hidden tray again."""
    with _connect() as conn:
        _experiment(conn, experiment_id)
        conn.execute("DELETE FROM experiment_hidden_tray WHERE experiment_id = ? AND tray_id = ?", (experiment_id, tray_id))


def record_tray_layout(
    experiment_id: int,
    kind: str,
    *,
    made_at: str,
    details: dict,
    capture_id: int | None = None,
    suggestion_id: int | None = None,
) -> dict:
    """Save a suggested tray layout, a check against one, or the cancelling of one (#343); the
    saved row."""
    if kind not in ("suggestion", "check", "cancel"):
        raise ValueError(f"unknown tray layout kind {kind!r}")
    with _connect() as conn:
        _experiment(conn, experiment_id)  # LookupError for no such experiment
        cursor = conn.execute(
            "INSERT INTO tray_layout (experiment_id, kind, made_at, capture_id, suggestion_id, details)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (experiment_id, kind, made_at, capture_id, suggestion_id, json.dumps(details)),
        )
        layout_id = cursor.lastrowid
    return tray_layout(layout_id)


def tray_layout(layout_id: int) -> dict | None:
    """One saved tray layout, its details decoded; None when there is no such layout."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tray_layout WHERE id = ?", (layout_id,)).fetchone()
    return None if row is None else {**dict(row), "details": json.loads(row["details"])}


def latest_tray_layout(experiment_id: int, kind: str) -> dict | None:
    """The experiment's newest saved suggestion or check, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM tray_layout WHERE experiment_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (experiment_id, kind),
        ).fetchone()
    return None if row is None else tray_layout(row[0])


def latest_tray_layout_for(suggestion_id: int, kind: str) -> dict | None:
    """The newest check or cancel of suggestion `suggestion_id`, or None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM tray_layout WHERE suggestion_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (suggestion_id, kind),
        ).fetchone()
    return None if row is None else tray_layout(row[0])


def experiment_calibrations(experiment_id: int) -> list[str | None]:
    """The calibrations the experiment's photos were taken under, each once (None for photos with
    none), for whether a cached reading of them is still current (#332)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT calibration FROM capture WHERE experiment_id = ? ORDER BY calibration", (experiment_id,)
        ).fetchall()
    return [row[0] for row in rows]


def experiment_tray_reads_mark(experiment_id: int) -> tuple:
    """A mark that changes whenever a photo of the experiment is read or read again (#332): the
    database, its photos read and when the newest was, and its tray readings' rows, newest row and
    centres."""
    with _connect() as conn:
        reads = conn.execute(
            "SELECT COUNT(*), MAX(tray_read.read_at) FROM tray_read JOIN capture ON capture.id = tray_read.capture_id"
            " WHERE capture.experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        rows = conn.execute(
            "SELECT COUNT(*), MAX(tray_reading.id), TOTAL(centre_x_px), TOTAL(centre_y_px), TOTAL(tray_id)"
            " FROM tray_reading JOIN capture ON capture.id = tray_reading.capture_id WHERE capture.experiment_id = ?",
            (experiment_id,),
        ).fetchone()
    return (str(db_path()), *reads, *rows)


def experiment_shared_tray_photos(experiment_id: int) -> set[int]:
    """Capture ids of the experiment's photos in which two tags lie in one tray outline found in
    the photo (`two tags in one outline`, #331), or, in readings saved before #331, two trays were
    placed in one slot (`two trays in one slot`): a tray carried over the table, or a loose tag on
    a tray (#315)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT tray_reading.capture_id FROM tray_reading"
            " JOIN capture ON capture.id = tray_reading.capture_id"
            " WHERE capture.experiment_id = ?"
            " AND tray_reading.placement IN ('two trays in one slot', 'two tags in one outline')",
            (experiment_id,),
        ).fetchall()
    return {row[0] for row in rows}


def unread_photos(limit: int, since: str) -> list[str]:
    """Paths of up to `limit` photos taken as captures (not validation, calibration or tripwire
    rounds) that have not been read for trays, newest first: those taken at or after `since` (UTC,
    when the reader started) and every photo of the running experiment. Older photos are read
    only when asked (Aaron, 2026-10-22)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT path FROM capture WHERE purpose = 'capture'"
            " AND id NOT IN (SELECT capture_id FROM tray_read)"
            " AND (taken_at >= ? OR experiment_id IN"
            " (SELECT experiment_id FROM experiment_period WHERE ended_at IS NULL))"
            " ORDER BY taken_at DESC LIMIT ?",
            (since, limit),
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
    dwell_limit_h: float | None = None,
) -> dict:
    """A new experiment, set up. `dwell_limit_h`: hours a tray may stay in one table location
    before the page warns (#332); None keeps the column's default, 4 days."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO experiment (uuid, name, researcher, tray_height_mm, notes, interval_s,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid, name, researcher, tray_height_mm, notes, interval_s, created_at),
        )
        if dwell_limit_h is not None:
            conn.execute("UPDATE experiment SET dwell_limit_h = ? WHERE id = ?", (dwell_limit_h, cursor.lastrowid))
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
# The photo interval can change at any time; a change while running counts slots from then. So can
# how long a tray may stay in one table location: the warning is worked out from the readings each time.
_EDITABLE = {
    "set up": {"name", "researcher", "tray_height_mm", "notes", "interval_s", "dwell_limit_h"},
    "purged": {"notes"},
}
_EDITABLE_LATER = {"name", "researcher", "notes", "interval_s", "dwell_limit_h"}


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
        conn.execute("DELETE FROM experiment_hidden_tray WHERE experiment_id = ?", (experiment_id,))
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


def save_photo_quality(changed_at: str, quality: int, chroma: str) -> None:
    """Save the photo quality setting (`camera_settings`, settings.PHOTO_QUALITY_SETTING) and
    record the change, in one transaction, so a setting never changes without its row (#359)."""
    from npec_rig.settings import CAMERA_SETTINGS_DDL, PHOTO_QUALITY_SETTING

    with _connect() as conn:
        conn.execute(CAMERA_SETTINGS_DDL)
        conn.execute(
            "INSERT INTO camera_settings (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (PHOTO_QUALITY_SETTING, json.dumps({"quality": quality, "chroma": chroma})),
        )
        conn.execute(
            "INSERT INTO photo_quality_change (changed_at, quality, chroma) VALUES (?, ?, ?)",
            (changed_at, quality, chroma),
        )


def photo_quality_changes() -> list[dict]:
    """Every change of the photo quality setting, newest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT changed_at, quality, chroma FROM photo_quality_change ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def record_app_start(started_at: str) -> None:
    with _connect() as conn:
        conn.execute("INSERT INTO app_start (started_at) VALUES (?)", (started_at,))


def app_starts(after: str) -> list[str]:
    """When the app started since `after`, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT started_at FROM app_start WHERE started_at > ? ORDER BY started_at", (after,)
        ).fetchall()
    return [started_at for (started_at,) in rows]


def scheduled_photos_taken(experiment_id: int, schedule_since: str) -> list[dict]:
    """{"due_at", "taken_at"} of each scheduled photo taken, oldest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT s.due_at, c.taken_at FROM scheduled_photo s JOIN capture c ON c.id = s.capture_id"
            " WHERE s.experiment_id = ? AND s.schedule_since = ? ORDER BY s.slot",
            (experiment_id, schedule_since),
        ).fetchall()
    return [{"due_at": due_at, "taken_at": taken_at} for due_at, taken_at in rows]


def schedule_progress(experiment_id: int, schedule_since: str) -> dict:
    """The last slot recorded (0 before the first), photos taken and missed, the missed ones
    counted by reason, and when the last photo was due."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(slot), 0), COUNT(capture_id), COUNT(missed_reason),"
            " MAX(CASE WHEN capture_id IS NOT NULL THEN due_at END)"
            " FROM scheduled_photo WHERE experiment_id = ? AND schedule_since = ?",
            (experiment_id, schedule_since),
        ).fetchone()
        reasons = conn.execute(
            "SELECT missed_reason, COUNT(*) FROM scheduled_photo WHERE experiment_id = ?"
            " AND schedule_since = ? AND missed_reason IS NOT NULL GROUP BY missed_reason",
            (experiment_id, schedule_since),
        ).fetchall()
    return {
        "last_slot": row[0],
        "photos_taken": row[1],
        "photos_missed": row[2],
        "missed_reasons": dict(reasons),
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
    """Mark a stopped experiment purged, delete its photo rows, their tray readings and
    exclusions, and mark its exports removed, in one transaction. The caller deletes the folder afterwards."""
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if _experiment(conn, experiment_id)["state"] != "stopped":
            raise ExperimentError("only a stopped experiment can be purged")
        photos = "SELECT id FROM capture WHERE experiment_id = ?"
        conn.execute(f"DELETE FROM tray_reading WHERE capture_id IN ({photos})", (experiment_id,))
        conn.execute(f"DELETE FROM cell_reading WHERE capture_id IN ({photos})", (experiment_id,))
        conn.execute(f"DELETE FROM tray_read WHERE capture_id IN ({photos})", (experiment_id,))
        conn.execute(f"DELETE FROM exclusion WHERE capture_id IN ({photos})", (experiment_id,))
        conn.execute("DELETE FROM capture WHERE experiment_id = ?", (experiment_id,))
        conn.execute(
            "UPDATE export SET removed_at = ? WHERE experiment_id = ? AND removed_at IS NULL",
            (now, experiment_id),
        )
        conn.execute("UPDATE experiment SET purged_at = ? WHERE id = ?", (now, experiment_id))
        return _experiment(conn, experiment_id)
