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


def test_the_page_and_its_routes() -> None:
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    assert client.get("/experiments").status_code == 200

    first = client.post("/api/experiments", json={"name": "  ", "researcher": "Lisa"}).json()
    assert first["name"] is None
    assert first["researcher"] == "Lisa"
    second = client.post("/api/experiments", json={}).json()

    assert client.post(f"/api/experiments/{first['id']}/start").json()["state"] == "running"
    refused = client.post(f"/api/experiments/{second['id']}/start")
    assert refused.status_code == 409
    assert "another experiment is running" in refused.json()["detail"]
    started = client.post(f"/api/experiments/{second['id']}/start", params={"stop_running": True})
    assert started.json()["state"] == "running"

    locked = client.patch(f"/api/experiments/{second['id']}", json={"tray_height_mm": 50})
    assert locked.status_code == 409
    renamed = client.patch(f"/api/experiments/{second['id']}", json={"name": "Drought"}).json()
    assert renamed["name"] == "Drought"

    assert client.post(f"/api/experiments/{second['id']}/stop").json()["state"] == "stopped"
    assert client.delete(f"/api/experiments/{second['id']}").status_code == 409
    assert client.post("/api/experiments/999/stop").status_code == 404
    states = {e["id"]: e["state"] for e in client.get("/api/experiments").json()}
    assert states == {first["id"]: "stopped", second["id"]: "stopped"}


def _reprocessed(client, experiment_id: int) -> dict:
    """Start Reprocess and wait for it to finish; its last progress."""
    import time

    assert client.post(f"/api/experiments/{experiment_id}/reprocess").status_code == 200
    deadline = time.monotonic() + 30
    while True:
        progress = client.get(f"/api/experiments/{experiment_id}/reprocess").json()
        if not progress["running"]:
            return progress
        assert time.monotonic() < deadline, "Reprocess did not finish"
        time.sleep(0.05)


def test_reprocess_fills_in_the_area_of_an_experiment_photo_that_has_none(monkeypatch) -> None:
    """`one_tray_plant_scene`: 1500 mm2 of plant inside tray 5, worked out by hand. The photo is
    taken during the experiment but never read, as the potato run's photos before areas existed."""
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app
    from tests.helpers import one_tray_plant_scene

    one_tray_plant_scene(monkeypatch)
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    _array, record = captures.take_photo("capture")
    del _array
    captures.stop_experiment(experiment["id"])
    assert tray_readings.photo_readings(record["path"]) is None

    progress = _reprocessed(TestClient(app), experiment["id"])

    assert (progress["done"], progress["total"]) == (1, 1)
    tray = tray_readings.photo_readings(record["path"])["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)


def test_reprocess_recounts_from_the_saved_mask_without_segmenting_again(monkeypatch) -> None:
    """The photo is read once (its mask saved), then its file is deleted: an area after Reprocess
    can only come from the mask. 1500 mm2 as `one_tray_plant_scene`."""
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app
    from npec_rig.captures import photo_file
    from tests.helpers import one_tray_plant_scene

    one_tray_plant_scene(monkeypatch)
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    _array, record = captures.take_photo("capture")
    del _array
    captures.stop_experiment(experiment["id"])
    tray_readings.read_photo(record["path"])
    photo_file(record["path"]).unlink()

    progress = _reprocessed(TestClient(app), experiment["id"])

    assert (progress["done"], progress["failed"]) == (1, 0)
    tray = tray_readings.photo_readings(record["path"])["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)


def test_reprocess_keeps_a_photos_areas_when_it_can_no_longer_work_them_out(monkeypatch) -> None:
    """Review of #287: a photo read with areas, whose file and mask are then both gone, cannot be
    segmented or counted again. Reprocess must leave its saved areas as they were and count it as
    failed, not replace them with none (lost data). 1500 mm2 as `one_tray_plant_scene`."""
    from fastapi.testclient import TestClient

    from npec_rig import segmentation, tray_readings
    from npec_rig.app import app
    from npec_rig.captures import photo_file
    from tests.helpers import one_tray_plant_scene

    one_tray_plant_scene(monkeypatch)
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    _array, record = captures.take_photo("capture")
    del _array
    captures.stop_experiment(experiment["id"])
    tray_readings.read_photo(record["path"])
    photo_file(record["path"]).unlink()
    segmentation.mask_file(record["path"]).unlink()

    progress = _reprocessed(TestClient(app), experiment["id"])

    assert (progress["done"], progress["failed"]) == (1, 1)
    tray = tray_readings.photo_readings(record["path"])["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)
