import threading

import pytest

from npec_rig import captures, database, exclusions, exports
from npec_rig.database import ExperimentError
from tests.helpers import export_built

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


def _stopped(name: str | None = "Drought", photos: int = 1) -> dict:
    experiment = captures.start_experiment(captures.create_experiment(name=name)["id"])
    for _ in range(photos):
        _array, _record = captures.take_photo("capture")
        del _array
    return captures.stop_experiment(experiment["id"])


def _exported(experiment: dict) -> dict:
    """Exported through the page's route, every part downloaded in full."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    export = export_built(client, experiment['id'])
    for part in export["parts"]:
        assert client.get(f"/api/exports/{export['id']}/parts/{part['n']}").status_code == 200
    return database.get_export(export["id"])


def test_purge_deletes_the_folder_and_rows_and_keeps_the_record() -> None:
    experiment = _stopped(photos=2)
    export = _exported(experiment)
    folder = captures.experiments_root() / experiment["folder"]
    _array, rig_photo = captures.take_photo("calibration")
    del _array

    purged = captures.purge_experiment(experiment["id"], confirm="Drought")

    assert purged["state"] == "purged"
    assert purged["name"] == "Drought"
    assert purged["purged_at"] is not None
    assert not folder.exists()
    assert database.captures_for_experiment(experiment["id"]) == []
    assert database.get_export(export["id"])["removed_at"] is not None
    assert database.captures_by_path([rig_photo["path"]])  # rig photos are never touched
    assert (captures.photos_root() / rig_photo["date"] / rig_photo["filename"]).exists()


def test_only_a_stopped_experiment_can_be_purged() -> None:
    running = captures.start_experiment(captures.create_experiment(name="Live")["id"])
    with pytest.raises(ExperimentError, match="only a stopped experiment"):
        captures.purge_experiment(running["id"], confirm="Live", override_no_export=True)
    set_up = captures.create_experiment(name="New")
    with pytest.raises(ExperimentError, match="only a stopped experiment"):
        captures.purge_experiment(set_up["id"], confirm="New", override_no_export=True)


def test_the_typed_text_must_match() -> None:
    experiment = _stopped()
    with pytest.raises(ExperimentError, match='you typed "drought", and purging needs exactly "Drought"'):
        captures.purge_experiment(experiment["id"], confirm="drought", override_no_export=True)
    with pytest.raises(ExperimentError, match='you typed "nothing"'):
        captures.purge_experiment(experiment["id"], confirm="  ", override_no_export=True)
    assert database.get_experiment(experiment["id"])["state"] == "stopped"


def test_an_unnamed_experiment_is_confirmed_by_its_folder_name() -> None:
    experiment = _stopped(name=None)
    assert captures.purge_confirmation(experiment) == experiment["folder"]
    purged = captures.purge_experiment(
        experiment["id"], confirm=experiment["folder"], override_no_export=True
    )
    assert purged["state"] == "purged"


def test_without_a_complete_export_purge_needs_the_override() -> None:
    experiment = _stopped()
    with pytest.raises(ExperimentError, match="no complete export"):
        captures.purge_experiment(experiment["id"], confirm="Drought")
    assert captures.purge_experiment(
        experiment["id"], confirm="Drought", override_no_export=True
    )["state"] == "purged"


def test_a_partial_export_followed_by_more_photos_is_not_complete() -> None:
    experiment = captures.start_experiment(captures.create_experiment(name="D")["id"])
    _array, _record = captures.take_photo("capture")
    _exported(experiment)
    _array, _record = captures.take_photo("capture")
    del _array
    captures.stop_experiment(experiment["id"])
    assert database.complete_export(experiment["id"]) is None
    assert _exported(experiment)["id"] == database.complete_export(experiment["id"])["id"]


def test_a_purged_experiment_cannot_be_resumed_exported_or_renamed() -> None:
    experiment = _stopped()
    captures.purge_experiment(experiment["id"], confirm="Drought", override_no_export=True)
    with pytest.raises(ExperimentError, match="purged"):
        captures.start_experiment(experiment["id"])
    with pytest.raises(ExperimentError, match="purged"):
        database.create_export(experiment["id"], now="t")
    with pytest.raises(ExperimentError, match="only the notes"):
        captures.update_experiment(experiment["id"], name="New name")
    assert captures.update_experiment(experiment["id"], notes="handed over")["notes"] == "handed over"


def test_purge_through_the_route() -> None:
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped()
    export = _exported(experiment)
    client = TestClient(app)
    listed = {e["id"]: e for e in client.get("/api/experiments").json()}
    assert listed[experiment["id"]]["complete_export"]["id"] == export["id"]
    assert listed[experiment["id"]]["purge_confirmation"] == "Drought"

    wrong = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "x"})
    assert wrong.status_code == 409
    done = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})
    assert done.json()["state"] == "purged"
    assert client.get(f"/api/exports/{export['id']}/parts/1").status_code == 409


def test_purge_deletes_the_experiments_plant_masks_and_keeps_rig_photos_masks() -> None:
    import numpy as np

    from npec_rig import segmentation

    experiment = _stopped()
    _exported(experiment)
    still = database.captures_for_experiment(experiment["id"])[0]["path"]
    _array, rig_photo = captures.take_photo("capture")
    del _array
    mask = np.zeros((4, 4), dtype=bool)
    segmentation.save_mask(still, mask)
    segmentation.save_mask(rig_photo["path"], mask)

    captures.purge_experiment(experiment["id"], confirm="Drought")

    assert segmentation.load_mask(still) is None
    assert segmentation.load_mask(rig_photo["path"]) is not None


def test_purge_deletes_the_photos_exclusions() -> None:
    """Review of #299: a photo with a stored exclusion could not be deleted, so an experiment
    whose photos were read could not be purged."""
    experiment = _stopped(photos=2)
    photos = database.captures_for_experiment(experiment["id"])
    exclusions.update(photos[-1])
    assert database.exclusion(photos[0]["id"]) is not None

    purged = captures.purge_experiment(experiment["id"], confirm="Drought", override_no_export=True)

    assert purged["state"] == "purged"
    assert [database.exclusion(p["id"]) for p in photos] == [None, None]


def test_a_data_only_export_is_not_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """#368 item 2: only an export holding every photo lets Purge through, or photos that were
    never exported could be deleted. Nothing covers the one photo at all (#482): `photos_added`,
    the reason that also covers a plain late photo."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped()
    client = TestClient(app)
    started = export_built(client, experiment["id"], {"data": True, "photos": False})
    assert client.get(f"/api/exports/{started['id']}/parts/0").status_code == 200
    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "photos_added"
    assert detail["count"] == 1
    assert "export again" in detail["message"]


# --- The reason-coded Purge check (#482) -----------------------------------------------------


def test_purge_needs_part_0_even_when_every_photo_part_was_sent() -> None:
    """Every photo part sent is not enough (review of #378, finding 3): part 0 itself, from a Data
    export, is required too."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped()
    client = TestClient(app)
    export = export_built(client, experiment["id"])
    for part in export["parts"]:
        if part["n"] != 0:
            assert client.get(f"/api/exports/{export['id']}/parts/{part['n']}").status_code == 200

    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})

    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "part0_unsent"
    assert client.get("/api/experiments").json()[0]["complete_export"] is None


def test_purge_blocks_on_a_photo_captured_after_the_export() -> None:
    """A photo captured after the export's list was fixed is not covered by it, however recently
    the export itself was made (#482)."""
    experiment = _stopped()
    _exported(experiment)
    captures.start_experiment(experiment["id"])
    _array, _record = captures.take_photo("capture")
    del _array
    captures.stop_experiment(experiment["id"])

    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "photos_added"
    assert detail["count"] == 1


def test_purge_blocks_when_a_photo_missing_at_build_has_since_appeared() -> None:
    """A photo whose file could not be found when the export was built is not covered, even once
    the file is there again: there is no record it was ever verifiably sent (#482)."""
    experiment = _stopped(photos=2)
    photos = database.captures_for_experiment(experiment["id"])
    stem = captures.experiments_root() / photos[0]["path"].removeprefix("experiments/")
    saved_jpg, saved_json = stem.with_suffix(".jpg").read_bytes(), stem.with_suffix(".json").read_bytes()
    stem.with_suffix(".jpg").unlink()
    stem.with_suffix(".json").unlink()

    export = _exported(experiment)
    # Still missing: nothing on the rig this export failed to cover, so Purge is not blocked by it
    # (database.complete_export, the simpler check captures.purge_experiment makes on its own, is
    # more conservative and always wants every file recorded sent; exports.purge_status, behind
    # the route below, is the one this test is about).
    assert exports.purge_status(experiment["id"])["blocked"] is None

    stem.with_suffix(".jpg").write_bytes(saved_jpg)
    stem.with_suffix(".json").write_bytes(saved_json)

    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "photos_added"
    assert detail["count"] == 1
    assert export["id"]  # the export itself is otherwise unaffected


def test_a_photo_missing_only_its_jpg_is_not_covered_by_its_json_having_sent() -> None:
    """A capture's .jpg and .json are two separate stored files (#482 review): if only the .jpg
    was missing when the export was built, its .json being sent must not count as the capture
    being covered. Forgiven while the .jpg stays missing (nothing to lose), but if it reappears
    before Purge, Purge must refuse, exactly as for a photo missing entirely."""
    experiment = _stopped(photos=2)
    photos = database.captures_for_experiment(experiment["id"])
    stem = captures.experiments_root() / photos[0]["path"].removeprefix("experiments/")
    saved_jpg = stem.with_suffix(".jpg").read_bytes()
    stem.with_suffix(".jpg").unlink()  # only the .jpg is missing; its .json stays and is sent

    _exported(experiment)
    assert exports.purge_status(experiment["id"])["blocked"] is None  # forgiven: still missing

    stem.with_suffix(".jpg").write_bytes(saved_jpg)  # it reappears before Purge

    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail["reason"] == "photos_added"
    assert detail["count"] == 1


def test_purge_blocks_after_a_reprocess_finished_since_the_export_even_if_stopped() -> None:
    """A Reprocess changes readings already inside a downloaded zip (#483); Purge refuses once one
    has finished since, whole or stopped partway through."""
    experiment = _stopped()
    export = _exported(experiment)
    run_id = database.create_reprocess_run(experiment["id"], total=1, started_at="2026-11-25T00:00:00+00:00")
    database.update_reprocess_run(run_id, done=1, failed=0, state="stopped", finished_at="2099-01-01T00:00:00+00:00")

    from fastapi.testclient import TestClient

    from npec_rig.app import app

    client = TestClient(app)
    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})

    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "reprocessed"
    assert export["id"]


def test_purge_succeeds_with_a_photo_never_read_for_trays() -> None:
    """A photo the scheduler has not read for trays yet (no calibration set up, ordinary for a
    running experiment) does not block Purge: only verifiably sent data does (#482)."""
    experiment = _stopped()
    assert database.tray_reading_count(experiment["id"]) == 0  # nothing has read this photo yet
    _exported(experiment)

    purged = captures.purge_experiment(experiment["id"], confirm="Drought")

    assert purged["state"] == "purged"


def _photo_file_without_a_row(experiment: dict, *, readable: bool = True) -> str:
    """A photo as the rig saves one while rig.db is locked: its JPEG and info file on disk, no
    row. A copy of the experiment's first photo under a new name; with `readable` False its
    info file is empty, as after a power cut. Returns its path as rig.db stores it."""
    first = next((captures.experiments_root() / experiment["folder"] / "stills").rglob("*.jpg"))
    jpeg = first.with_name("235959_000001.jpg")
    jpeg.write_bytes(first.read_bytes())
    jpeg.with_suffix(".json").write_text(first.with_suffix(".json").read_text() if readable else "")
    return f"experiments/{experiment['folder']}/stills/{first.parent.name}/{jpeg.stem}"


def test_purge_adds_a_missing_row_first_and_so_asks_for_a_new_export() -> None:
    """#489: a photo with no row was left out of every export, and Purge deleted it with the
    folder. Purge now adds the row first, and refuses until the photo is exported."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped()
    _exported(experiment)
    path = _photo_file_without_a_row(experiment)

    refused = TestClient(app).post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})

    assert refused.status_code == 409
    assert refused.json()["detail"]["reason"] == "photos_added"
    assert database.captures_by_path([path])


def test_purge_check_counts_the_photos_that_cannot_be_given_a_row_and_purge_still_goes_ahead() -> None:
    """#489 (Aaron, 2026-11-23): try to add the rows, warn with the number that failed, and let
    Purge go ahead."""
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped()
    client = TestClient(app)
    readable = _photo_file_without_a_row(experiment)
    assert client.post(f"/api/experiments/{experiment['id']}/purge-check").json() == {"photos_without_row": 0}
    assert database.captures_by_path([readable])  # the check added its row

    damaged = captures.experiments_root() / experiment["folder"] / "stills"
    next(damaged.rglob("235959_000001.json")).with_name("235959_000002.json").write_text("")
    next(damaged.rglob("235959_000001.jpg")).with_name("235959_000002.jpg").write_bytes(b"x")
    assert client.post(f"/api/experiments/{experiment['id']}/purge-check").json() == {"photos_without_row": 1}

    purged = client.post(
        f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought", "override_no_export": True}
    )
    assert purged.json()["state"] == "purged"


def test_purge_check_says_to_try_again_while_rig_db_is_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """#489: the check cannot add a row while rig.db is locked, and says so (503) rather than
    reporting that no photos are without one."""
    from fastapi.testclient import TestClient

    from npec_rig import settings
    from npec_rig.app import app
    from tests.helpers import lock_held

    experiment = _stopped()
    path = _photo_file_without_a_row(experiment)
    client = TestClient(app)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.05)

    with lock_held(30, until=(checked := threading.Event())):
        response = client.post(f"/api/experiments/{experiment['id']}/purge-check")
        checked.set()

    monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
    assert response.status_code == 503
    assert "try again" in response.json()["detail"]
    assert database.captures_by_path([path]) == {}  # no row was added
