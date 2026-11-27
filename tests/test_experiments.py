import json
import shutil
import sqlite3

import pytest

from npec_rig import captures, database
from npec_rig.database import ExperimentError
from npec_rig.settings import db_path
from tests.helpers import needs_ffmpeg, video_done, video_held

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))
    yield
    # No export build outlives its test (#437): it would write into the next test's folders.
    from npec_rig import exports

    exports.fail_unfinished_exports()


# --- The experiment the Reprocess tests start from, built once for the module (#547) --------------
# Taking one photo of `one_tray_plant_scene` costs about 0.3 s and reading one about 0.75 s, and
# sixteen tests below start from the same handful of states made only of those two steps. Each
# state is built here once and kept in a folder of its own; a test asks for one by name and gets a
# copy of it in its own temp folders, so a test that deletes a photo, writes rows or runs Reprocess
# cannot be seen by any other test and the order the tests run in does not matter.

# Every folder and file the rig writes, as the per-test fixtures above and in tests/conftest.py lay
# them out under one root: copying a root copies a whole rig state.
_ROOT_FOLDERS = {
    "NPEC_RIG_PHOTOS_DIR": "rig",
    "NPEC_RIG_EXPERIMENTS_DIR": "experiments",
    "NPEC_RIG_CALIBRATION_DIR": "calibration",
    "NPEC_RIG_DERIVED_DIR": "derived",
    "NPEC_RIG_MASKS_DIR": "masks",
}


def _point_at(patch: pytest.MonkeyPatch, root) -> None:
    """Point the rig at `root`: its photos, experiments, calibrations, derived images, masks and
    rig.db all under that one folder."""
    for name, folder in _ROOT_FOLDERS.items():
        patch.setenv(name, str(root / folder))
    patch.setenv("NPEC_RIG_DB_PATH", str(root / "rig.db"))


@pytest.fixture(scope="module")
def _twin_states(tmp_path_factory) -> dict[str, tuple]:
    """Each starting state as (its folder, the experiment's ID, its photo paths), built once.

    `"<n> unread"`: a stopped experiment with `n` photos of `one_tray_plant_scene` taken as
    captures and never read. `"<n> read"`: the same, with each photo read once, so its areas are
    saved in rig.db and its mask on disk. The experiment is the first one made, so its ID is 1.
    """
    import npec_rig.camera as camera_module
    from npec_rig import tray_readings
    from npec_rig.camera import CameraManager
    from tests.helpers import one_tray_plant_scene

    source = tmp_path_factory.mktemp("twin-states")
    states: dict[str, tuple] = {}
    with pytest.MonkeyPatch.context() as patch:
        # The same lens-drive waits the per-test fixtures drop (tests/conftest.py): they run after
        # this one, so this build would otherwise wait where no test does.
        patch.setattr(camera_module, "LENS_APPROACH_PAUSE_S", 0.0)
        patch.setattr(camera_module, "LENS_POLL_INTERVAL_S", 0.0)
        running = source / "running"
        _point_at(patch, running)
        one_tray_plant_scene(patch)
        experiment = captures.start_experiment(captures.create_experiment()["id"])
        paths: list[str] = []
        for count in (1, 2, 3):
            _array, record = captures.take_photo("capture")
            del _array
            paths.append(record["path"])
            root = source / f"{count}-unread"
            shutil.copytree(running, root)
            # The copy is stopped and kept; `running` stays running, for the next photo.
            _point_at(patch, root)
            captures.stop_experiment(experiment["id"])
            states[f"{count} unread"] = (root, experiment["id"], tuple(paths))
            _point_at(patch, running)
        for count in (1, 2):
            unread, experiment_id, taken = states[f"{count} unread"]
            root = source / f"{count}-read"
            shutil.copytree(unread, root)
            _point_at(patch, root)
            for path in taken:
                tray_readings.read_photo(path)
            states[f"{count} read"] = (root, experiment_id, taken)
    CameraManager.set_instance(None)  # the scene's camera does not outlive the build
    return states


@pytest.fixture
def twin(_twin_states, monkeypatch, tmp_path, isolated_folders, isolated_settings_db):
    """Start a test from one of `_twin_states`: copies that state into this test's own folders and
    gives back the experiment's ID and its photo paths. The copy is the test's alone."""
    from tests.helpers import one_tray_plant_scene

    def start_from(state: str) -> tuple[int, list[str]]:
        root, experiment_id, paths = _twin_states[state]
        for entry in root.iterdir():
            if entry.is_dir():
                shutil.copytree(entry, tmp_path / entry.name, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, tmp_path / entry.name)
        # The camera, the tag and the calibration the copied photos were taken with: Reprocess
        # reads a photo's tags again through `photo_tags.detect_tags`.
        one_tray_plant_scene(monkeypatch)
        return experiment_id, list(paths)

    return start_from


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

    assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
    deadline = time.monotonic() + 30
    while True:
        progress = client.get(f"/api/experiments/{experiment_id}/reprocess").json()
        if not progress["running"]:
            return progress
        assert time.monotonic() < deadline, "Reprocess did not finish"
        time.sleep(0.05)


def test_reprocess_fills_in_the_area_of_an_experiment_photo_that_has_none(twin) -> None:
    """`one_tray_plant_scene`: 1500 mm2 of plant inside tray 5, worked out by hand. The photo is
    taken during the experiment but never read, as the potato run's photos before areas existed."""
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app

    experiment_id, [path] = twin("1 unread")
    assert tray_readings.photo_readings(path) is None

    progress = _reprocessed(TestClient(app), experiment_id)

    assert (progress["done"], progress["total"]) == (1, 1)
    tray = tray_readings.photo_readings(path)["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)


def test_reprocess_recounts_from_the_saved_mask_without_segmenting_again(twin) -> None:
    """The photo is read once (its mask saved), then its file is deleted: an area after Reprocess
    can only come from the mask. 1500 mm2 as `one_tray_plant_scene`."""
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app
    from npec_rig.captures import photo_file

    experiment_id, [path] = twin("1 read")
    photo_file(path).unlink()

    progress = _reprocessed(TestClient(app), experiment_id)

    assert (progress["done"], progress["failed"]) == (1, 0)
    tray = tray_readings.photo_readings(path)["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)


def test_reprocess_keeps_a_photos_areas_when_it_can_no_longer_work_them_out(twin) -> None:
    """Review of #287: a photo read with areas, whose file and mask are then both gone, cannot be
    segmented or counted again. Reprocess must leave its saved areas as they were and count it as
    failed, not replace them with none (lost data). 1500 mm2 as `one_tray_plant_scene`."""
    from fastapi.testclient import TestClient

    from npec_rig import segmentation, tray_readings
    from npec_rig.app import app
    from npec_rig.captures import photo_file

    experiment_id, [path] = twin("1 read")
    photo_file(path).unlink()
    segmentation.mask_file(path).unlink()

    progress = _reprocessed(TestClient(app), experiment_id)

    assert (progress["done"], progress["failed"]) == (1, 1)
    tray = tray_readings.photo_readings(path)["trays"][0]
    assert tray["area_mm2"] == pytest.approx(1500, rel=0.01)


def test_reprocess_reads_an_experiment_again_with_the_rebuilt_twin(twin) -> None:
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

    stem = json.loads((Path(__file__).parent / "fixtures" / "trays" / "shuffles-2026-10-20.json").read_text())["calibration"]
    experiment_id, paths = twin("2 read")
    photos = {p: photo_file(p).read_bytes() for p in paths}
    masks = {p: segmentation.load_mask(p) for p in paths}
    rebuilt = "20261026T150000000001"  # the twin's own stem; `twin` is the fixture above
    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-26T15:00:00+00:00", scale_field=ScaleField((1.0, 0.0, 0.0), 10.0 * 5.00 / 4.90, 0.0),
            frame_stem=stem, lens_position=6.05, rebuilt_from=stem,
        ),
        stem=rebuilt, promote=False,
    )

    progress = _reprocessed(TestClient(app), experiment_id)

    assert (progress["done"], progress["failed"]) == (2, 0)
    for p in paths:
        tray = tray_readings.photo_readings(p)["trays"][0]
        assert tray["area_mm2"] == pytest.approx(1440.6, rel=0.01)  # 1%: JPEG blurs the edge
        assert tray["calibration"] == rebuilt
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
        from tests.helpers import export_built

        export = export_built(client, experiment_id, {"data": True, "photos": False})
        with zipfile.ZipFile(io.BytesIO(client.get(f"/api/exports/{export['id']}/parts/0").content)) as zf:
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


def test_the_experiments_page_has_one_data_button_per_experiment_in_place_of_the_export_buttons() -> None:
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    page = TestClient(app).get("/experiments").text

    # The rows are drawn by the page's script: its buttons are named in it (#454).
    assert 'button("data", "Data")' in page
    assert 'button("export"' not in page
    assert 'button("parts"' not in page
    assert "Data export" not in page
    assert "/api/exports/${x.id}/download" not in page


# --- The Reprocess API (#483, PR B): dry run, confirmation, Stop, saved progress ---------------------


def _experiment_with_photos(twin, count: int) -> tuple[int, list[str]]:
    """An experiment stopped after `count` photos of `one_tray_plant_scene` taken as captures,
    none of them read: this test's own copy of the state `_twin_states` built once."""
    return twin(f"{count} unread")


def test_a_reprocess_dry_run_counts_the_photos_and_changes_nothing(twin) -> None:
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app

    experiment_id, paths = _experiment_with_photos(twin, 2)
    client = TestClient(app)

    response = client.post(f"/api/experiments/{experiment_id}/reprocess", json={"dry_run": True})

    assert response.status_code == 200
    assert response.json()["photos"] == 2
    assert response.json()["estimated_seconds"] is None  # no earlier Reprocess to take a time from
    assert client.get(f"/api/experiments/{experiment_id}/reprocess").json()["state"] == "none"
    assert [tray_readings.photo_readings(p) for p in paths] == [None, None]


def test_a_reprocess_without_the_experiment_id_confirmed_starts_nothing(twin) -> None:
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app

    experiment_id, paths = _experiment_with_photos(twin, 1)
    client = TestClient(app)

    for body in ({}, {"confirm": experiment_id + 1}):
        response = client.post(f"/api/experiments/{experiment_id}/reprocess", json=body)
        assert response.status_code == 400
        assert f"confirm" in response.json()["detail"]
    assert client.get(f"/api/experiments/{experiment_id}/reprocess").json()["state"] == "none"
    assert tray_readings.photo_readings(paths[0]) is None


def test_reprocess_stops_after_the_photo_it_is_reading(monkeypatch, twin) -> None:
    """Three photos; Stop is asked while the second is being read (its tags are searched then). The
    second finishes, the third is not read: 2 of 3 done, the run says it was stopped."""
    import time

    from fastapi.testclient import TestClient

    from npec_rig import photo_tags, tray_readings
    from npec_rig.app import app

    experiment_id, paths = _experiment_with_photos(twin, 3)
    client = TestClient(app)
    tags = photo_tags.detect_tags  # the scene's own, as `one_tray_plant_scene` set it
    calls = []

    def detect_and_stop(frame):
        calls.append(1)
        if len(calls) == 2:
            assert client.post(f"/api/experiments/{experiment_id}/reprocess/stop").status_code == 200
        return tags(frame)

    monkeypatch.setattr(photo_tags, "detect_tags", detect_and_stop)
    assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
    deadline = time.monotonic() + 30
    while client.get(f"/api/experiments/{experiment_id}/reprocess").json()["running"]:
        assert time.monotonic() < deadline
        time.sleep(0.05)

    progress = client.get(f"/api/experiments/{experiment_id}/reprocess").json()
    assert (progress["state"], progress["done"], progress["total"]) == ("stopped", 2, 3)
    assert progress["message"] == "stopped at 2 of 3"
    assert [tray_readings.photo_readings(p) is not None for p in paths] == [True, True, False]


def test_a_failed_photo_is_listed_with_its_reason_and_kept_in_rig_db(twin) -> None:
    """The photo and its masks are gone, so it cannot be redone: its saved reading stays, and the
    run keeps its path and why, in rig.db, for the next time the page or a script asks."""
    from fastapi.testclient import TestClient

    from npec_rig import segmentation
    from npec_rig.app import app
    from npec_rig.captures import photo_file

    experiment_id, [path] = twin("1 read")
    photo_file(path).unlink()
    segmentation.mask_file(path).unlink()

    progress = _reprocessed(TestClient(app), experiment_id)

    assert (progress["state"], progress["done"], progress["failed"]) == ("finished", 1, 1)
    [failure] = progress["failures"]
    assert failure["path"] == path
    assert "saved mask" in failure["reason"]
    saved = database.latest_reprocess_run(experiment_id)  # what a restarted app reads
    assert (saved["state"], saved["failures"]) == ("finished", progress["failures"])


def test_a_reprocess_left_running_when_the_app_stopped_is_marked_interrupted_and_not_resumed(twin) -> None:
    from fastapi.testclient import TestClient

    from npec_rig import tray_readings
    from npec_rig.app import app

    experiment_id, paths = _experiment_with_photos(twin, 1)
    run = database.create_reprocess_run(experiment_id, total=10, started_at="2026-11-24T10:00:00+00:00")
    database.update_reprocess_run(run, done=3, failed=1)
    client = TestClient(app)

    tray_readings.mark_interrupted_reprocesses()  # the app's start-up

    progress = client.get(f"/api/experiments/{experiment_id}/reprocess").json()
    assert (progress["state"], progress["running"], progress["done"], progress["total"]) == ("interrupted", False, 3, 10)
    assert progress["message"] == "interrupted at 3 of 10"
    assert tray_readings.photo_readings(paths[0]) is None  # nothing was resumed
    assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
    _wait_until_finished(client, experiment_id)  # its thread ends before the next test starts


# How long the locker below waits for the photo's tags to be stored before it gives up. The
# reading stores them in well under a second even on a loaded Pi, so this only has to be longer
# than that; it is reached only when they are never stored at all. Absolute, in whole seconds,
# because it covers real work on an unknown machine (#576).
TAGS_STORED_TIMEOUT_S = 30.0


def _lock_once_the_reading_is_segmenting(path: str, *, until=None, seconds: float = 5.0):
    """A thread that takes rig.db's write lock once the photo's reading is segmenting, so that
    saving the reading is the first write to meet it; started by the caller, joined at the end.

    Segmenting, not merely "the tags are stored". The tags can already be stored when this
    starts, and the lock then went up before the request that starts the Reprocess: that
    request's own write met it and the test failed with `database is locked` at the POST, which
    is neither what it asserts nor a fault in the rig. 2 failures in 8 full runs on an idle Pi
    (#576). Taking the full-decode slot is strictly after the request and strictly before the
    reading saves anything, so it settles the order instead of racing it -- the same move #561
    made for the sibling test.

    Waiting for the stored tags first is what makes the slot mean segmentation: the tag search
    holds the same slot and stores the tags as it lets go, so the next thread to take it is this
    reading's own segmentation.

    Both waits have a deadline and the thread is a daemon: with neither, a run where the tags
    were never stored polled for ever and pytest could not exit at all (#576)."""
    import threading
    import time

    from npec_rig import images
    from tests.helpers import lock_held

    def ended() -> bool:
        return until is not None and until.is_set()

    def run() -> None:
        slot = images.full_decode_slot()
        deadline = time.monotonic() + TAGS_STORED_TIMEOUT_S
        while images.stored_tag_detections(path) is None:
            if ended():
                return  # the test has already finished
            assert time.monotonic() < deadline, (
                f"the photo's tags were not stored within {TAGS_STORED_TIMEOUT_S} s: {path}"
            )
            time.sleep(0.001)
        while slot.acquire(timeout=0.01):  # free: the reading is not segmenting yet
            slot.release()
            if ended():
                return
            assert time.monotonic() < deadline, (
                f"the reading never took the full-decode slot to segment within "
                f"{TAGS_STORED_TIMEOUT_S} s: {path}"
            )
            time.sleep(0.005)
        with lock_held(seconds, until=until):
            if until is not None:
                until.wait(seconds)

    return threading.Thread(target=run, daemon=True)


def _wait_until_finished(client, experiment_id: int, timeout_s: float = 30) -> dict:
    """Poll the Reprocess progress route until the run has ended.

    Through read_rig_db: the tests that lock rig.db shorten settings.LOCK_WAIT_S, and
    database._connect gives that same short wait to every connection, including the one this
    route reads on. A poll landing while something commits then raised
    `sqlite3.OperationalError: database is locked` out of the route, which TestClient re-raises,
    and the test failed for its own read rather than for the rig's behaviour. 1 failure in 8 full
    runs on an idle Pi, and the same mechanism failed the Arm64 CI runner on #575 (#576)."""
    import time

    from tests.helpers import read_rig_db

    deadline = time.monotonic() + timeout_s
    while True:
        progress = read_rig_db(
            lambda: client.get(f"/api/experiments/{experiment_id}/reprocess").json()
        )
        if not progress["running"]:
            return progress
        assert time.monotonic() < deadline, "Reprocess did not finish"
        time.sleep(0.05)


def test_a_photo_that_meets_a_rig_db_lock_is_tried_again(monkeypatch, twin) -> None:
    """The lock is taken as the photo's reading is about to be saved and let go when the first
    failure to save is logged: the photo is read on the next try and the run reports no failure."""
    import logging
    import threading

    from fastapi.testclient import TestClient

    from npec_rig import settings, tray_readings
    from npec_rig.app import app

    experiment_id, [path] = _experiment_with_photos(twin, 1)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.1)
    monkeypatch.setattr(tray_readings, "REPROCESS_LOCK_WAIT_S", 0.05)
    gave_up = threading.Event()

    class FirstLockFailure(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if "was locked" in record.getMessage():
                gave_up.set()

    handler = FirstLockFailure()
    logging.getLogger("npec_rig.database").addHandler(handler)
    locker = _lock_once_the_reading_is_segmenting(path, until=gave_up)
    client = TestClient(app)
    try:
        locker.start()
        assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
        progress = _wait_until_finished(client, experiment_id)
    finally:
        gave_up.set()
        locker.join(15)
        logging.getLogger("npec_rig.database").removeHandler(handler)

    assert (progress["state"], progress["done"], progress["failed"]) == ("finished", 1, 0)
    assert tray_readings.photo_readings(path)["status"] == "read"


def test_a_photo_that_stays_locked_is_given_up_after_the_cap_and_listed(monkeypatch, twin) -> None:
    """The lock is held through the 3 tries of the cap and let go when the run logs that it gave
    the photo up, so the failure itself can be saved: the photo is listed as failed with the reason.

    The lock has to be up before the run's first write and after the run row the request itself
    writes, and the tags are stored before it so that only writes meet it (#561). Both are settled
    here rather than raced: the tags are searched up front, and this test holds
    `images.full_decode_slot()` from before the request, so the run cannot get past segmenting the
    photo -- its last step before it saves anything -- until the lock is up and the slot let go."""
    import logging
    import threading
    import time

    from fastapi.testclient import TestClient

    from npec_rig import images, photo_tags, settings, tray_readings
    from npec_rig.app import app
    from tests.helpers import lock_held

    experiment_id, [path] = _experiment_with_photos(twin, 1)
    photo_tags.photo_tags_for(path)  # its tags stored before the lock, so only writes meet it
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.05)
    monkeypatch.setattr(tray_readings, "REPROCESS_LOCK_WAIT_S", 0.01)
    monkeypatch.setattr(tray_readings, "REPROCESS_LOCK_TRIES", 3)
    gave_the_photo_up = threading.Event()

    class GaveUp(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.getMessage().startswith("Reprocess could not read"):
                gave_the_photo_up.set()

    handler = GaveUp()
    logging.getLogger("npec_rig.tray_readings").addHandler(handler)
    client = TestClient(app)
    slot = images.full_decode_slot()
    # Timed: this is the one process-global decode slot, shared with the tag search and with every
    # other test in this xdist worker, and there is no pytest-timeout here. An untimed acquire
    # would block the worker for ever if anything else were holding the slot -- no output, no test
    # named, CI reporting a 20-minute timeout instead of a failure.
    assert slot.acquire(timeout=30), "the full-decode slot was already held"  # the run waits here
    holding_slot = True
    # The lock is let go the moment the run gives the photo up, so this cap is only reached when
    # something is wrong; 60 s is about 23x the 2.55 s the run spends under it on this box.
    lock_cap_s = 60
    try:
        assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
        with lock_held(lock_cap_s, until=gave_the_photo_up):
            slot.release()
            holding_slot = False
            try:
                # The lock only proves anything if the run meets it while segmenting, so wait for
                # the run to really take the slot. Without this the test passes even if the run
                # never touches the slot (a recount path that skips _segment, a segmenter that
                # does not decode full size, a scene whose trays are not outlined): the lock would
                # then simply be up before an unheld run, which is the race this test is meant to
                # have no part of. The run needs about 300 ms of work before _segment and holds
                # the slot about 490 ms once there, against the 15 ms this loop takes to notice.
                took_the_slot = time.monotonic() + 15
                while slot.acquire(timeout=0.01):  # free: the run is not segmenting yet
                    slot.release()
                    assert time.monotonic() < took_the_slot, "the run never took the full-decode slot to segment"
                    time.sleep(0.005)
                progress = _wait_until_finished(client, experiment_id)
                gave_up_under_the_lock = gave_the_photo_up.is_set()
            except BaseException:
                # Let the lock go now. lock_held joins its holder on the way out and the holder is
                # sitting in until.wait(lock_cap_s), so a failure here would otherwise be reported
                # only after the rest of the cap had run out.
                gave_the_photo_up.set()
                raise
    finally:
        gave_the_photo_up.set()
        if holding_slot:
            slot.release()
        logging.getLogger("npec_rig.tray_readings").removeHandler(handler)

    assert gave_up_under_the_lock, (
        f"the run did not give the photo up within the {lock_cap_s} s the lock was held: the lock "
        "dropped first and the run went on to succeed, which is this box being too slow for the "
        "cap, not the behaviour under test failing")
    assert (progress["done"], progress["failed"]) == (1, 1)
    [failure] = progress["failures"]
    assert failure["path"] == path
    assert "locked" in failure["reason"] and "3 tries" in failure["reason"]


def test_a_reprocess_that_could_not_save_its_end_does_not_block_the_next_one(monkeypatch, twin) -> None:
    """Second review of #483: rig.db stays locked for every try of the run's last write, so its row
    stays `running` though its thread has ended. No thread runs it, so it reads as interrupted and a
    new Reprocess starts (not 409 until a restart)."""
    import threading
    import time

    from fastapi.testclient import TestClient

    from npec_rig import photo_tags, settings, tray_readings
    from npec_rig.app import app
    from tests.helpers import lock_held

    experiment_id, [path] = _experiment_with_photos(twin, 1)
    photo_tags.photo_tags_for(path)  # its tags are stored before the lock, so only writes meet it
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.05)
    monkeypatch.setattr(tray_readings, "REPROCESS_LOCK_WAIT_S", 0.01)
    monkeypatch.setattr(tray_readings, "REPROCESS_LOCK_TRIES", 2)
    client = TestClient(app)

    assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
    with lock_held(20, until=(release := threading.Event())):  # taken while the first photo is still being read
        deadline = time.monotonic() + 15
        while any(t.name == "reprocess" for t in threading.enumerate()):
            assert time.monotonic() < deadline, "the run's thread did not end"
            time.sleep(0.05)
        release.set()

    progress = client.get(f"/api/experiments/{experiment_id}/reprocess").json()
    assert (progress["state"], progress["running"]) == ("interrupted", False)
    assert client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id}).status_code == 200
    _wait_until_finished(client, experiment_id)


def test_reprocess_of_an_experiment_that_never_started_is_refused_and_it_can_still_be_discarded() -> None:
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment_id = captures.create_experiment()["id"]
    client = TestClient(app)

    for body in ({"dry_run": True}, {"confirm": experiment_id}):
        response = client.post(f"/api/experiments/{experiment_id}/reprocess", json=body)
        assert 400 <= response.status_code < 500
        assert "never started" in response.json()["detail"]
    database.discard_experiment(experiment_id)  # no run row stands in the way


def test_discarding_an_experiment_removes_the_reprocess_rows_it_has() -> None:
    experiment_id = captures.create_experiment()["id"]
    run = database.create_reprocess_run(experiment_id, total=1, started_at="2026-11-24T10:00:00+00:00")
    database.add_reprocess_failure(run, path="p", reason="r", failed_at="2026-11-24T10:00:01+00:00")

    database.discard_experiment(experiment_id)

    with sqlite3.connect(db_path()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM reprocess_run").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM reprocess_failure").fetchone()[0] == 0


def test_a_confirm_that_is_not_the_experiment_id_as_a_number_starts_nothing(twin) -> None:
    """`true` is not 1: the experiment's ID must be sent as the number."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment_id, _paths = _experiment_with_photos(twin, 1)
    assert experiment_id == 1
    client = TestClient(app)

    response = client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": True})

    assert 400 <= response.status_code < 500
    assert client.get(f"/api/experiments/{experiment_id}/reprocess").json()["state"] == "none"


def _finished_run(experiment_id: int, done: int, failed: int, seconds: int, *, lock_failures: int = 0) -> None:
    run = database.create_reprocess_run(experiment_id, total=done, started_at="2026-11-24T10:00:00+00:00")
    for i in range(lock_failures):
        database.add_reprocess_failure(run, path=f"p{i}", reason="rig.db stayed locked after 5 tries", failed_at="2026-11-24T10:00:01+00:00")
    database.update_reprocess_run(run, done=done, failed=failed, state="finished",
                                  finished_at=f"2026-11-24T10:{seconds // 60:02d}:{seconds % 60:02d}+00:00")


def test_the_estimate_counts_the_photos_a_run_redid_not_the_ones_it_failed_at(twin) -> None:
    """A finished run of 4 photos, 2 of them failed, took 100 s: the 2 it redid took 50 s each, so
    the 2 photos of this experiment are estimated at 100 s. A run that redid none gives no estimate."""
    from npec_rig import tray_readings

    experiment_id, _paths = _experiment_with_photos(twin, 2)

    _finished_run(experiment_id, 2, 2, 5)  # redid none: no rate
    assert tray_readings.reprocess_plan(experiment_id)["estimated_seconds"] is None
    _finished_run(experiment_id, 4, 2, 100)
    assert tray_readings.reprocess_plan(experiment_id)["estimated_seconds"] == 100


def test_the_estimate_leaves_out_a_run_that_gave_a_photo_up_for_a_lock(twin) -> None:
    """Giving a photo up for a lock takes the tries' waits, so such a run says nothing of the time a
    photo takes: the estimate is from the run before it, 100 s for 2 photos, 50 s each."""
    from npec_rig import tray_readings

    experiment_id, _paths = _experiment_with_photos(twin, 2)
    _finished_run(experiment_id, 2, 0, 100)
    _finished_run(experiment_id, 3, 1, 10, lock_failures=1)

    assert tray_readings.reprocess_plan(experiment_id)["estimated_seconds"] == 100


def test_progress_is_still_given_while_rig_db_is_locked_for_a_run_with_no_thread(monkeypatch) -> None:
    """Second review of #501: a run left `running` (its last save met a lock) is shown as interrupted
    even while the lock lasts, the write that marks it waits for the lock to end: no 500."""
    import threading

    from fastapi.testclient import TestClient

    from npec_rig import settings
    from npec_rig.app import app
    from tests.helpers import lock_held

    experiment_id = captures.start_experiment(captures.create_experiment()["id"])["id"]
    database.create_reprocess_run(experiment_id, total=10, started_at="2026-11-24T10:00:00+00:00")
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.05)
    client = TestClient(app)

    # Let go the moment both pages have been asked for, rather than after a fixed 2 s (#547): what
    # is tested is that they answer while the lock lasts, not how long it lasts.
    with lock_held(2, until=(release := threading.Event())):
        one = client.get(f"/api/experiments/{experiment_id}/reprocess")
        listed = client.get("/api/experiments")
        release.set()
    assert (one.status_code, one.json()["state"], one.json()["running"]) == (200, "interrupted", False)
    assert listed.status_code == 200
    assert [e["reprocess"]["state"] for e in listed.json() if e["id"] == experiment_id] == ["interrupted"]
    assert client.get(f"/api/experiments/{experiment_id}/reprocess").json()["state"] == "interrupted"  # and now marked


def test_reprocess_of_a_purged_experiment_is_refused(twin) -> None:
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment_id, _paths = _experiment_with_photos(twin, 1)
    database.purge_experiment(experiment_id, now="2026-11-24T10:00:00+00:00")
    client = TestClient(app)

    for body in ({"dry_run": True}, {"confirm": experiment_id}):
        response = client.post(f"/api/experiments/{experiment_id}/reprocess", json=body)
        assert 400 <= response.status_code < 500
        assert "photos were deleted" in response.json()["detail"]


def test_progress_without_failures_never_has_the_failures_key(monkeypatch) -> None:
    from npec_rig import tray_readings

    experiment_id = captures.start_experiment(captures.create_experiment()["id"])["id"]
    assert "failures" not in tray_readings.reprocess_progress(experiment_id, failures=False)
    _finished_run(experiment_id, 1, 0, 5)
    assert "failures" not in tray_readings.reprocess_progress(experiment_id, failures=False)
    assert tray_readings.reprocess_progress(experiment_id)["failures"] == []


# --- One job that reads every photo at a time: a Reprocess waits for a time lapse video (#503) --

@needs_ffmpeg
def test_a_reprocess_is_refused_while_a_video_is_being_made_and_starts_once_it_is_done(monkeypatch, tmp_path, twin) -> None:
    from fastapi.testclient import TestClient

    from npec_rig import timelapse
    from npec_rig.app import app

    experiment_id, _paths = _experiment_with_photos(twin, 1)
    client = TestClient(app)
    video_id, release = video_held(experiment_id, monkeypatch, tmp_path)
    try:
        assert timelapse.being_made() == video_id
        refused = client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id})
        assert refused.status_code == 409
        assert "A time lapse video is being made" in refused.json()["detail"]
        assert client.get(f"/api/experiments/{experiment_id}/reprocess").json()["state"] == "none"
    finally:
        release.touch()
    video_done()

    started = client.post(f"/api/experiments/{experiment_id}/reprocess", json={"confirm": experiment_id})
    assert started.status_code == 200
    assert _wait_until_finished(client, experiment_id)["state"] == "finished"
