import json
import sqlite3

import pytest

from npec_rig import captures, database
from npec_rig.database import ExperimentError
from npec_rig.settings import db_path

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def test_version_1_photos_become_rig_photos() -> None:
    v1 = database.MIGRATIONS[:1]
    with sqlite3.connect(db_path()) as conn:
        conn.isolation_level = None
        for statement in v1[0][2]:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO capture (taken_at, path, purpose, flags)"
            " VALUES ('t', '2026-10-09/115050_239652', 'capture', '[]')"
        )
        conn.execute("PRAGMA user_version = 1")
        conn.isolation_level = ""
        assert database.migrate(conn) == database.SCHEMA_VERSION
        assert conn.execute("SELECT path FROM capture").fetchone()[0] == (
            "rig/2026-10-09/115050_239652"
        )


def test_the_database_refuses_two_running_experiments() -> None:
    first = captures.create_experiment()
    second = captures.create_experiment()
    with sqlite3.connect(db_path()) as conn:
        conn.execute(
            "INSERT INTO experiment_period (experiment_id, started_at) VALUES (?, 't')",
            (first["id"],),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO experiment_period (experiment_id, started_at) VALUES (?, 't')",
                (second["id"],),
            )


def test_set_up_start_stop_resume() -> None:
    experiment = captures.create_experiment(name="Flash drought", researcher="Lisa")
    assert experiment["state"] == "set up"
    assert experiment["folder"] is None

    experiment = captures.start_experiment(experiment["id"])
    assert experiment["state"] == "running"
    folder = captures.experiments_root() / experiment["folder"]
    assert experiment["folder"] == f"{experiment['periods'][0]['started_at'][:10]}_{experiment['uuid'][:8]}"
    assert json.loads((folder / "experiment.json").read_text())["name"] == "Flash drought"
    assert database.running_experiment()["id"] == experiment["id"]

    experiment = captures.stop_experiment(experiment["id"])
    assert experiment["state"] == "stopped"
    assert database.running_experiment() is None

    resumed = captures.start_experiment(experiment["id"])
    assert resumed["state"] == "running"
    assert resumed["folder"] == experiment["folder"]
    assert len(resumed["periods"]) == 2
    assert resumed["periods"][0]["ended_at"] is not None


def test_a_name_is_optional() -> None:
    assert captures.create_experiment()["name"] is None


def test_starting_while_another_runs_needs_stop_running() -> None:
    first = captures.start_experiment(captures.create_experiment()["id"])
    second = captures.create_experiment()
    with pytest.raises(ExperimentError, match="another experiment is running"):
        captures.start_experiment(second["id"])
    assert database.get_experiment(second["id"])["folder"] is None
    assert len(list(captures.experiments_root().iterdir())) == 1

    second = captures.start_experiment(second["id"], stop_running=True)
    assert second["state"] == "running"
    assert database.get_experiment(first["id"])["state"] == "stopped"


def test_tray_height_is_fixed_once_started() -> None:
    experiment = captures.create_experiment(tray_height_mm=75.0)
    captures.update_experiment(experiment["id"], tray_height_mm=80.0)
    captures.start_experiment(experiment["id"])
    with pytest.raises(ExperimentError, match="tray_height_mm cannot be changed"):
        captures.update_experiment(experiment["id"], tray_height_mm=90.0)
    renamed = captures.update_experiment(experiment["id"], name="Renamed", notes="day 3")
    assert renamed["tray_height_mm"] == 80.0
    folder = captures.experiments_root() / renamed["folder"]
    assert json.loads((folder / "experiment.json").read_text())["name"] == "Renamed"


def test_only_a_never_started_experiment_can_be_discarded() -> None:
    kept = captures.start_experiment(captures.create_experiment()["id"])
    with pytest.raises(ExperimentError):
        database.discard_experiment(kept["id"])
    gone = captures.create_experiment()
    database.discard_experiment(gone["id"])
    assert [e["id"] for e in database.list_experiments()] == [kept["id"]]


def test_an_existing_folder_is_never_shared(monkeypatch: pytest.MonkeyPatch) -> None:
    experiment = captures.create_experiment()
    monkeypatch.setattr(captures, "_now", lambda: "2026-10-09T12:00:00+00:00")
    (captures.experiments_root() / f"2026-10-09_{experiment['uuid'][:8]}").mkdir(parents=True)
    with pytest.raises(ExperimentError, match="already exists"):
        captures.start_experiment(experiment["id"])
    assert database.get_experiment(experiment["id"])["state"] == "set up"


def test_capture_photos_go_to_the_running_experiment_and_others_stay_in_rig() -> None:
    experiment = captures.start_experiment(captures.create_experiment(name="Drought")["id"])
    _array, capture = captures.take_photo("capture")
    _array, calibration = captures.take_photo("calibration")
    del _array

    day = capture["date"]
    stem = capture["filename"].removesuffix(".jpg")
    assert capture["path"] == f"experiments/{experiment['folder']}/stills/{day}/{stem}"
    assert capture["url"] == f"/experiment-files/{experiment['folder']}/stills/{day}/{capture['filename']}"
    assert (captures.experiments_root() / experiment["folder"] / "stills" / day / capture["filename"]).exists()
    assert capture["experiment"]["uuid"] == experiment["uuid"]
    assert calibration["path"].startswith("rig/")
    assert calibration["experiment"] is None

    rows = database.captures_by_path([capture["path"], calibration["path"]])
    assert rows[capture["path"]]["experiment_id"] == experiment["id"]
    assert rows[calibration["path"]]["experiment_id"] is None

    listed = {e["path"]: e for e in captures.list_recent_captures()}
    assert listed[capture["path"]]["record"]["experiment_id"] == experiment["id"]
    assert listed[calibration["path"]]["record"]["purpose"] == "calibration"


def test_after_stop_photos_are_rig_photos_again() -> None:
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    captures.stop_experiment(experiment["id"])
    _array, capture = captures.take_photo("capture")
    del _array
    assert capture["path"].startswith("rig/")
    assert capture["experiment"] is None
