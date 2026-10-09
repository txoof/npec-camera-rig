import sqlite3

import pytest

from npec_rig import captures, database
from npec_rig.settings import db_path, save_setting

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_photos_and_calibration(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    # Other tests leave a current calibration in conftest's shared folder.
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def test_a_new_database_gets_every_migration() -> None:
    with sqlite3.connect(db_path()) as conn:
        assert database.migrate(conn) == database.SCHEMA_VERSION
        assert _version(conn) == database.SCHEMA_VERSION
        columns = [row[1] for row in conn.execute("PRAGMA table_info(capture)")]
    assert columns[:4] == ["id", "taken_at", "path", "purpose"]


def test_migrating_twice_changes_nothing() -> None:
    with sqlite3.connect(db_path()) as conn:
        database.migrate(conn)
        conn.execute(
            "INSERT INTO capture (taken_at, path, purpose, flags) VALUES ('t', 'p', 'capture', '[]')"
        )
        conn.commit()
        assert database.migrate(conn) == database.SCHEMA_VERSION
        assert conn.execute("SELECT COUNT(*) FROM capture").fetchone()[0] == 1


def test_the_rigs_own_tables_are_left_alone() -> None:
    # rig.db today: version 0 with the housekeeping tables already in it.
    save_setting("ExposureTime", 20000)
    with sqlite3.connect(db_path()) as conn:
        assert _version(conn) == 0
        database.migrate(conn)
        rows = conn.execute("SELECT name FROM camera_settings").fetchall()
    assert rows == [("ExposureTime",)]


def test_a_database_newer_than_the_app_is_refused() -> None:
    with sqlite3.connect(db_path()) as conn:
        conn.execute(f"PRAGMA user_version = {database.SCHEMA_VERSION + 1}")
        with pytest.raises(RuntimeError, match="schema version"):
            database.migrate(conn)


def test_a_failed_migration_leaves_the_file_as_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    broken = database.MIGRATIONS + ((database.SCHEMA_VERSION + 1, "broken", ("NOT SQL",)),)
    monkeypatch.setattr(database, "MIGRATIONS", broken)
    monkeypatch.setattr(database, "SCHEMA_VERSION", database.SCHEMA_VERSION + 1)
    with sqlite3.connect(db_path()) as conn:
        with pytest.raises(sqlite3.Error):
            database.migrate(conn)
        assert _version(conn) == 0
        tables = conn.execute("SELECT name FROM sqlite_master WHERE name = 'capture'").fetchall()
    assert tables == []


def test_every_photo_gets_one_row() -> None:
    _array, capture = captures.take_photo("capture")
    _array, validation = captures.take_photo("validation", {"validation_session": "s1"})
    del _array

    paths = [f"{r['date']}/{r['filename'].removesuffix('.jpg')}" for r in (capture, validation)]
    rows = database.captures_by_path(paths)
    assert [rows[p]["id"] for p in paths] == [capture["capture_id"], validation["capture_id"]]
    row = rows[paths[0]]
    assert row["purpose"] == "capture"
    assert row["taken_at"] == capture["timestamp"]
    assert row["flags"] == capture["flags"]
    assert row["focus_locked_at"] is None
    assert row["experiment_id"] is None
    assert row["calibration"] is None


def test_a_database_failure_does_not_lose_the_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(**_fields: object) -> int:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(database, "record_capture", fail)
    _array, record = captures.take_photo("capture")
    del _array
    assert record["capture_id"] is None
    assert (captures.photos_root() / record["date"] / record["filename"]).exists()


def test_a_photo_records_the_calibration_active_when_it_was_taken() -> None:
    from npec_rig.calibration import CalibrationArtifact, ScaleField
    from npec_rig.calibration_store import save_calibration

    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-09T07:31:08+00:00",
            scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
            frame_stem="20261009T073108292325",
        )
    )
    _array, record = captures.take_photo("capture")
    del _array
    path = f"{record['date']}/{record['filename'].removesuffix('.jpg')}"
    assert database.captures_by_path([path])[path]["calibration"] == "20261009T073108292325"
