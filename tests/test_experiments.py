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


def test_reprocess_reads_an_experiment_again_with_the_rebuilt_twin(monkeypatch) -> None:
    """Part B, test point 4 (#286). Two photos of `one_tray_plant_scene` (150,000 plant px at 10.0
    px/mm, 1500 mm2), read once, so their masks are saved. After a twin is rebuilt at 10.0 x 5.00 /
    4.90 px/mm, Reprocess gives each 1500 x (4.90 / 5.00)^2 = 1440.6 mm2, names the twin as its
    calibration, and leaves the photos and masks as they were."""
    import json
    from pathlib import Path

    import numpy as np
    from fastapi.testclient import TestClient

    from npec_rig import segmentation, tray_readings
    from npec_rig.app import app
    from npec_rig.calibration import CalibrationArtifact, ScaleField
    from npec_rig.calibration_store import save_calibration
    from npec_rig.captures import photo_file
    from tests.helpers import one_tray_plant_scene

    one_tray_plant_scene(monkeypatch)
    stem = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())["calibration"]
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    paths = []
    for _ in range(2):
        _array, record = captures.take_photo("capture")
        del _array
        paths.append(record["path"])
        tray_readings.read_photo(record["path"])
    captures.stop_experiment(experiment["id"])
    photos = {p: photo_file(p).read_bytes() for p in paths}
    masks = {p: segmentation.load_mask(p) for p in paths}
    twin = "20261026T150000000001"
    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-26T15:00:00+00:00", scale_field=ScaleField((1.0, 0.0, 0.0), 10.0 * 5.00 / 4.90, 0.0),
            frame_stem=stem, lens_position=6.05, rebuilt_from=stem,
        ),
        stem=twin, promote=False,
    )

    progress = _reprocessed(TestClient(app), experiment["id"])

    assert (progress["done"], progress["failed"]) == (2, 0)
    for p in paths:
        tray = tray_readings.photo_readings(p)["trays"][0]
        assert tray["area_mm2"] == pytest.approx(1440.6, rel=0.01)  # 1%: JPEG blurs the edge
        assert tray["calibration"] == twin
        assert photo_file(p).read_bytes() == photos[p]
        assert np.array_equal(segmentation.load_mask(p), masks[p])


def test_how_long_a_tray_may_stay_in_one_location_defaults_to_4_days_and_can_be_changed_while_running() -> None:
    """Aaron, 2026-10-30 (#332): a setting on each experiment, default 4 days, kept in hours."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    plain = client.post("/api/experiments", json={}).json()
    assert plain["dwell_limit_h"] == 96
    two_days = client.post("/api/experiments", json={"dwell_limit_h": 48}).json()
    assert two_days["dwell_limit_h"] == 48

    client.post(f"/api/experiments/{plain['id']}/start")
    assert client.patch(f"/api/experiments/{plain['id']}", json={"dwell_limit_h": 144}).json()["dwell_limit_h"] == 144
    assert client.patch(f"/api/experiments/{plain['id']}", json={"dwell_limit_h": 0}).status_code == 422
    saved = {e["id"]: e["dwell_limit_h"] for e in client.get("/api/experiments").json()}
    assert saved == {plain["id"]: 144, two_days["id"]: 48}


def test_a_tray_over_its_limit_in_one_location_is_warned_for_on_the_page_in_words() -> None:
    """#332, limit 4 days: tray 7 in NW since 5 days ago (photos then and 1 hour ago) is too long
    there; tray 8 in SE since 3 days ago is not."""
    from datetime import UTC, datetime, timedelta

    from fastapi.testclient import TestClient

    from npec_rig.app import app
    from tests.helpers import table_calibration, table_photo

    table_calibration()
    client = TestClient(app)
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")
    now = datetime.now(UTC)
    # Never missing over 48 hours (database.NOT_SEEN_FOR): that would end a stay.
    table_photo(experiment["id"], now - timedelta(days=5), {7: "NW"})
    table_photo(experiment["id"], now - timedelta(days=4), {7: "NW"})
    for ago in (timedelta(days=3), timedelta(days=1.5), timedelta(hours=1)):
        table_photo(experiment["id"], now - ago, {7: "NW", 8: "SE"})

    page = client.get(f"/experiments/{experiment['id']}/table-locations")
    assert page.status_code == 200
    assert "Tray 7: too long in NW, 5.0 days" in page.text
    assert "Tray 8: too long" not in page.text
    listed = {e["id"]: e for e in client.get("/api/experiments").json()}[experiment["id"]]
    assert [(w["tray_id"], w["location"]) for w in listed["dwell_warnings"]] == [(7, "NW")]


def _two_trays_running(client) -> int:
    """A running experiment with trays 7 (NW since 5 days ago, over the 4 day limit) and 12 (SE
    since 1 day ago, under it)."""
    from datetime import UTC, datetime, timedelta

    from tests.helpers import table_calibration, table_photo

    table_calibration()
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")
    now = datetime.now(UTC)
    # Never missing over 48 hours (database.NOT_SEEN_FOR): that would end a stay.
    table_photo(experiment["id"], now - timedelta(days=5), {7: "NW"})
    table_photo(experiment["id"], now - timedelta(days=3), {7: "NW"})
    table_photo(experiment["id"], now - timedelta(days=1), {7: "NW", 12: "SE"})
    table_photo(experiment["id"], now - timedelta(hours=1), {7: "NW", 12: "SE"})
    return experiment["id"]


def test_a_hidden_tray_shows_as_one_line_until_shown_again() -> None:
    """Aaron, 2026-11-02 (#332): a misread tag, such as 12, can be hidden on the panel."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    experiment_id = _two_trays_running(client)
    full_view = "Tray 12, hours in each location"

    assert client.post(f"/api/experiments/{experiment_id}/trays/12/hide").status_code == 200
    page = client.get(f"/experiments/{experiment_id}/table-locations").text
    assert "Tray 12, hidden" in page
    assert full_view not in page
    assert "Tray 7, hours in each location" in page

    assert client.post(f"/api/experiments/{experiment_id}/trays/12/show").status_code == 200
    page = client.get(f"/experiments/{experiment_id}/table-locations").text
    assert "Tray 12, hidden" not in page
    assert full_view in page


def test_a_hidden_tray_stays_hidden_on_a_fresh_page_load() -> None:
    """Kept in rig.db: every PC and a restart show it hidden (#332)."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment_id = _two_trays_running(TestClient(app))
    TestClient(app).post(f"/api/experiments/{experiment_id}/trays/12/hide")

    with TestClient(app) as fresh:  # a new client, with the app started again
        assert "Tray 12, hidden" in fresh.get(f"/experiments/{experiment_id}/table-locations").text


def test_a_hidden_tray_gives_no_warning_and_the_export_is_unchanged() -> None:
    """Tray 7 is 5 days in NW, over the 4 day limit; hidden, it is warned for nowhere. Its hours stay
    in the export: 5 days less 1 hour in NW, 119.00 h, as before it was hidden."""
    import csv
    import io
    import zipfile

    from fastapi.testclient import TestClient

    from npec_rig import exports
    from npec_rig.app import app

    client = TestClient(app)
    experiment_id = _two_trays_running(client)

    def export_rows() -> list[list[str]]:
        export = database.create_export(experiment_id, now=exports._now())
        exports._build(export["id"], experiment_id)
        with zipfile.ZipFile(exports.zip_path(database.get_export(export["id"]))) as zf:
            name = next(n for n in zf.namelist() if n.endswith("time-in-table-location.csv"))
            return list(csv.reader(io.StringIO(zf.read(name).decode())))

    before = export_rows()
    client.post(f"/api/experiments/{experiment_id}/trays/7/hide")

    page = client.get(f"/experiments/{experiment_id}/table-locations").text
    assert "Tray 7: too long" not in page
    assert "No tray too long in one location" in page
    listed = {e["id"]: e for e in client.get("/api/experiments").json()}[experiment_id]
    assert listed["dwell_warnings"] == []
    assert export_rows() == before
    assert before[1][:2] == ["7", "119.00"]


def test_the_panel_stacks_every_shown_tray_on_one_timeline_and_leaves_out_hidden_ones() -> None:
    """Aaron, 2026-11-02 (#332): one strip per tray on a shared time axis, each named by its
    locations in order. Tray 7 was in NW, tray 12 in SE; tray 12 hidden is left out of it."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    experiment_id = _two_trays_running(client)
    page = client.get(f"/experiments/{experiment_id}/table-locations").text
    assert 'aria-label="Tray 7 over time: NW"' in page
    assert 'aria-label="Tray 12 over time: SE"' in page

    client.post(f"/api/experiments/{experiment_id}/trays/12/hide")
    page = client.get(f"/experiments/{experiment_id}/table-locations").text
    assert 'aria-label="Tray 7 over time: NW"' in page
    assert "Tray 12 over time" not in page
    assert "Hidden from this timeline: tray 12." in page


def test_a_tray_taken_away_and_back_in_the_same_location_is_not_a_move_on_the_panel() -> None:
    """#332: missing over 48 hours ends a stay; back in NW, the new stay is in NW, not a move."""
    from datetime import UTC, datetime, timedelta

    from fastapi.testclient import TestClient

    from npec_rig.app import app
    from tests.helpers import table_calibration, table_photo

    table_calibration()
    client = TestClient(app)
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")
    now = datetime.now(UTC)
    table_photo(experiment["id"], now - timedelta(days=4), {7: "NW"})
    table_photo(experiment["id"], now - timedelta(hours=1), {7: "NW"})

    page = client.get(f"/experiments/{experiment['id']}/table-locations")
    assert page.status_code == 200
    assert "NW to NW" not in page.text
