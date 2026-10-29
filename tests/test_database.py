import sqlite3

import pytest

from npec_rig import captures, database
from npec_rig.settings import db_path, save_setting
from tests.helpers import stored_validation

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

    paths = [r["path"] for r in (capture, validation)]
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
    _calibrate()
    _array, record = captures.take_photo("capture")
    del _array
    path = record["path"]
    assert database.captures_by_path([path])[path]["calibration"] == _STEM


_STEM = "20261009T073108292325"


def _calibrate(lens_position: float = 6.04) -> None:
    from npec_rig.calibration import CalibrationArtifact, ScaleField
    from npec_rig.calibration_store import save_calibration

    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-09T07:31:08+00:00",
            scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
            frame_stem=_STEM,
            lens_position=lens_position,
        )
    )


def _locked(at: float | None) -> dict:
    return {"locked": at is not None, "lens_position": at}


def test_the_validation_is_stored_for_a_capture_but_not_judged_for_a_validation_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _calibrate()
    stored_validation("20261009T100000000000", _STEM)
    monkeypatch.setattr(captures.CameraManager.instance(), "focus_status", lambda: _locked(6.04))
    _array, capture = captures.take_photo("capture")
    _array, round_ = captures.take_photo("validation", {"validation_session": "s1"})
    del _array

    assert capture["validation"]["session"] == "20261009T100000000000"
    assert "validation" not in round_
    paths = [r["path"] for r in (capture, round_)]
    rows = database.captures_by_path(paths)
    assert rows[paths[0]]["validation"] == "20261009T100000000000"
    assert rows[paths[1]]["validation"] is None


def test_the_gallery_list_carries_each_photos_record() -> None:
    _array, record = captures.take_photo("capture")
    del _array
    (captures.photos_root() / "2026-01-01").mkdir()
    old = captures.photos_root() / "2026-01-01" / "000000_000000"
    old.with_suffix(".jpg").write_bytes(b"")

    entries = {e["filename"]: e for e in captures.list_recent_captures()}
    assert entries[record["filename"]]["record"]["id"] == record["capture_id"]
    assert entries["000000_000000.jpg"]["record"] is None


# --- Tray readings (#222) ---


def _photo(taken_at: str, experiment_id: int | None = None) -> int:
    return database.record_capture(
        taken_at=taken_at, path=f"rig/{taken_at}", purpose="capture", experiment_id=experiment_id,
        calibration=None, validation=None, lens_position=None, focus_locked_at=None,
        exposure_us=None, analogue_gain=None, flags=[],
    )


def _tray(tray_id: int, slot: str = "N1") -> dict:
    return {
        "tray_id": tray_id, "slot": slot, "a1_corner": "SW", "placement": "placed",
        "centre_px": [4000.0, 3000.0], "tilt_deg": 1.5, "margin_mm": 120.0,
    }


def test_a_photos_tray_readings_are_saved_and_read_back() -> None:
    capture_id = _photo("2026-10-21T07:00:00+00:00")
    database.record_tray_readings(
        capture_id, read_at="2026-10-21T07:00:10+00:00", status="read", trays=[_tray(3, "N2"), _tray(1)]
    )

    readings = database.tray_readings(capture_id)
    assert readings["status"] == "read"
    assert readings["read_at"] == "2026-10-21T07:00:10+00:00"
    assert [(t["tray_id"], t["slot"]) for t in readings["trays"]] == [(1, "N1"), (3, "N2")]
    assert readings["trays"][0]["centre_px"] == [4000.0, 3000.0]
    assert readings["trays"][0]["area_mm2"] is None


def _experiment() -> int:
    experiment = database.create_experiment(uuid="u-222", created_at="2026-10-21T06:00:00+00:00")
    database.start_experiment(experiment["id"], now="2026-10-21T06:00:00+00:00", folder="experiments/x")
    return experiment["id"]


def _read(taken_at: str, tray_ids: list[int], experiment_id: int | None) -> int:
    capture_id = _photo(taken_at, experiment_id)
    database.record_tray_readings(capture_id, read_at=taken_at, status="read", trays=[_tray(t) for t in tray_ids])
    return capture_id


def test_a_tray_seen_earlier_in_the_experiment_shows_as_not_found_since_it_went_missing() -> None:
    experiment_id = _experiment()
    _read("2026-10-21T07:00:00+00:00", [1, 2], experiment_id)
    _read("2026-10-21T07:01:00+00:00", [1], experiment_id)
    third = _read("2026-10-21T07:02:00+00:00", [1], experiment_id)

    assert database.tray_readings(third)["not_found"] == [
        {"tray_id": 2, "slot": "N1", "since": "2026-10-21T07:01:00+00:00", "photos": 2}
    ]


def test_a_tray_not_found_names_the_slot_it_was_last_found_in_even_after_moving() -> None:
    """#318: the gallery shows the empty slot, so it is the newest slot, not the first."""
    experiment_id = _experiment()
    first = _photo("2026-10-21T07:00:00+00:00", experiment_id)
    database.record_tray_readings(first, read_at="t", status="read", trays=[_tray(1, "North 1"), _tray(8, "North 5")])
    second = _photo("2026-10-21T07:01:00+00:00", experiment_id)
    database.record_tray_readings(second, read_at="t", status="read", trays=[_tray(1, "North 1"), _tray(8, "North 6")])
    third = _read("2026-10-21T07:02:00+00:00", [1], experiment_id)

    assert database.tray_readings(third)["not_found"] == [
        {"tray_id": 8, "slot": "North 6", "since": "2026-10-21T07:02:00+00:00", "photos": 1}
    ]


def test_purging_an_experiment_removes_its_tray_readings() -> None:
    experiment_id = _experiment()
    capture_id = _read("2026-10-21T07:00:00+00:00", [1], experiment_id)
    database.stop_experiment(experiment_id, now="2026-10-21T08:00:00+00:00")

    database.purge_experiment(experiment_id, now="2026-10-21T09:00:00+00:00")
    assert database.tray_readings(capture_id) is None


def test_a_swapped_tag_shows_the_new_tray_found_and_the_old_one_not_found() -> None:
    experiment_id = _experiment()
    _read("2026-10-21T07:00:00+00:00", [12], experiment_id)
    swapped = _read("2026-10-21T07:01:00+00:00", [13], experiment_id)
    # A rig photo outside the experiment says nothing about its trays.
    _read("2026-10-21T07:00:30+00:00", [5], None)

    readings = database.tray_readings(swapped)
    assert [t["tray_id"] for t in readings["trays"]] == [13]
    assert readings["not_found"] == [{"tray_id": 12, "slot": "N1", "since": "2026-10-21T07:01:00+00:00", "photos": 1}]


def test_a_tray_moved_or_turned_since_the_previous_photo_is_listed_as_moved() -> None:
    experiment_id = _experiment()
    first = _photo("2026-10-21T07:00:00+00:00", experiment_id)
    database.record_tray_readings(first, read_at="t", status="read", trays=[_tray(1, "North 1"), _tray(2, "North 2")])
    second = _photo("2026-10-21T07:01:00+00:00", experiment_id)
    database.record_tray_readings(
        second, read_at="t", status="read", trays=[_tray(1, "South 3"), {**_tray(2, "North 2"), "a1_corner": "NE"}]
    )

    assert database.tray_readings(first)["moved"] == []
    assert database.tray_readings(second)["moved"] == [
        {"tray_id": 1, "from": ["North 1", "SW"], "to": ["South 3", "SW"]},
        {"tray_id": 2, "from": ["North 2", "SW"], "to": ["North 2", "NE"]},
    ]


def test_a_photo_with_no_tags_at_all_is_not_counted_as_trays_missing() -> None:
    """Metrology log 15.5l: with the lights off no tag is found, which says nothing about trays."""
    experiment_id = _experiment()
    _read("2026-10-21T21:00:00+00:00", [1, 2], experiment_id)
    dark = _photo("2026-10-21T21:01:00+00:00", experiment_id)
    database.record_tray_readings(dark, read_at="t", status="no tags found", trays=[])
    morning = _read("2026-10-21T21:02:00+00:00", [1], experiment_id)

    assert database.tray_readings(dark)["not_found"] == []
    assert database.tray_readings(morning)["not_found"] == [
        {"tray_id": 2, "slot": "N1", "since": "2026-10-21T21:02:00+00:00", "photos": 1}
    ]


def test_unread_photos_come_newest_first_so_new_photos_are_not_stuck_behind_old_ones() -> None:
    for taken_at in ("2026-10-21T07:00:00+00:00", "2026-10-21T07:02:00+00:00", "2026-10-21T07:01:00+00:00"):
        _photo(taken_at)
    _read("2026-10-21T07:03:00+00:00", [1], None)  # read already: left out

    assert database.unread_photos(limit=2, since="2026-10-21T00:00:00+00:00") == [
        "rig/2026-10-21T07:02:00+00:00", "rig/2026-10-21T07:01:00+00:00"
    ]


def test_older_photos_are_left_for_on_demand_unless_their_experiment_is_running() -> None:
    """Aaron, 2026-10-22: photos from before the reader started are read only when asked, except
    those of the running experiment."""
    _photo("2026-10-21T06:00:00+00:00")  # an old rig photo: on demand
    stopped = database.create_experiment(uuid="u-old", created_at="2026-10-20T06:00:00+00:00")
    database.start_experiment(stopped["id"], now="2026-10-20T06:00:00+00:00", folder="experiments/old")
    _photo("2026-10-20T07:00:00+00:00", stopped["id"])  # an old experiment's photo: on demand
    database.stop_experiment(stopped["id"], now="2026-10-20T08:00:00+00:00")
    running = _experiment()
    _photo("2026-10-21T06:30:00+00:00", running)  # before the start, but its experiment runs
    _photo("2026-10-21T07:30:00+00:00")  # taken since the reader started

    assert database.unread_photos(limit=10, since="2026-10-21T07:00:00+00:00") == [
        "rig/2026-10-21T07:30:00+00:00", "rig/2026-10-21T06:30:00+00:00"
    ]


def test_versions_13_and_14_keep_every_saved_tray_reading_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """#302: version 13 copies tray_reading into a table without its one-row-per-tag rule; #331:
    version 14 into one where a tray found in the photo may have no tag. A row saved at version 12
    comes through with every value in its own column."""
    with monkeypatch.context() as m:
        m.setattr(database, "MIGRATIONS", database.MIGRATIONS[:12])
        m.setattr(database, "SCHEMA_VERSION", 12)
        with sqlite3.connect(db_path()) as conn:
            database.migrate(conn)
            conn.execute("INSERT INTO capture (id, taken_at, path, purpose, flags) VALUES (9, 't', 'p', 'capture', '[]')")
            conn.execute("INSERT INTO tray_read (capture_id, read_at, status) VALUES (9, 'r', 'read')")
            conn.execute(
                "INSERT INTO tray_reading (id, capture_id, tray_id, slot, a1_corner, placement, centre_x_px,"
                " centre_y_px, tilt_deg, margin_mm, area_mm2, segmenter, plant_px, plant_centre_x_px,"
                " plant_centre_y_px, calibration, outside_mm) VALUES"
                " (4, 9, 1, 'North 4', 'NE', 'close call', 10.5, 20.5, -1.5, 40.5, 1234.5, 'green', 678,"
                " 11.5, 21.5, '20261026T153214381640', 3.5)"
            )
            conn.commit()
    with sqlite3.connect(db_path()) as conn:
        assert database.migrate(conn) == 14
        row = conn.execute(
            "SELECT id, capture_id, tray_id, slot, a1_corner, placement, centre_x_px, centre_y_px, tilt_deg,"
            " margin_mm, area_mm2, segmenter, plant_px, plant_centre_x_px, plant_centre_y_px, calibration,"
            " outside_mm FROM tray_reading"
        ).fetchall()
    assert row == [(4, 9, 1, "North 4", "NE", "close call", 10.5, 20.5, -1.5, 40.5, 1234.5, "green", 678,
                    11.5, 21.5, "20261026T153214381640", 3.5)]


def test_a_tray_found_in_the_photo_keeps_how_it_was_found_its_warnings_and_its_outline() -> None:
    """#331: an outline with no tag has no tray ID, slot, A1 corner or margin."""
    capture_id = _photo("2026-10-29T07:00:00+00:00")
    outline = [[100.0, 200.0], [3150.0, 200.0], [3150.0, 3860.0], [100.0, 3860.0]]
    untagged = {
        "tray_id": None, "slot": None, "a1_corner": None, "placement": "placed", "centre_px": [1625.0, 2030.0],
        "tilt_deg": 0.0, "margin_mm": None, "found": "photo, no tag", "warnings": ["no tag"], "outline_px": outline,
    }
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[untagged])

    [tray] = database.tray_readings(capture_id)["trays"]
    assert (tray["tray_id"], tray["slot"], tray["a1_corner"], tray["margin_mm"]) == (None, None, None, None)
    assert (tray["found"], tray["warnings"], tray["outline_px"]) == ("photo, no tag", ["no tag"], outline)


def _untagged(slot: str | None = "N1") -> dict:
    return {**_tray(0, slot), "tray_id": None, "a1_corner": None, "margin_mm": None, "found": "photo, no tag",
            "warnings": ["no tag"]}


def test_a_tray_with_no_tag_never_hides_a_tray_not_found_and_is_never_one_itself() -> None:
    experiment_id = _experiment()
    first = _photo("2026-10-29T07:00:00+00:00", experiment_id)
    database.record_tray_readings(first, read_at="t", status="read", trays=[_tray(1), _tray(2), _untagged()])
    second = _photo("2026-10-29T07:01:00+00:00", experiment_id)
    database.record_tray_readings(second, read_at="t", status="read", trays=[_tray(1), _untagged()])
    third = _photo("2026-10-29T07:02:00+00:00", experiment_id)
    database.record_tray_readings(third, read_at="t", status="read", trays=[_tray(1)])

    assert database.tray_readings(second)["not_found"] == [
        {"tray_id": 2, "slot": "N1", "since": "2026-10-29T07:01:00+00:00", "photos": 1}
    ]
    assert [t["tray_id"] for t in database.tray_readings(third)["not_found"]] == [2]


def test_a_tray_with_no_tag_is_never_listed_as_moved() -> None:
    experiment_id = _experiment()
    first = _photo("2026-10-29T07:00:00+00:00", experiment_id)
    database.record_tray_readings(first, read_at="t", status="read", trays=[_tray(1), _untagged("N2")])
    second = _photo("2026-10-29T07:01:00+00:00", experiment_id)
    database.record_tray_readings(second, read_at="t", status="read", trays=[_tray(1), _untagged("S3")])

    assert database.tray_readings(second)["moved"] == []
