import time
import pytest

from npec_rig import captures, database, exclusions, exports
from npec_rig.database import ExperimentError

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _stopped(name: str | None = "Drought", photos: int = 1) -> dict:
    experiment = captures.start_experiment(captures.create_experiment(name=name)["id"])
    for _ in range(photos):
        _array, _record = captures.take_photo("capture")
        del _array
    return captures.stop_experiment(experiment["id"])


def _exported(experiment: dict) -> dict:
    export = database.create_export(experiment["id"], now=exports._now())
    exports._build(export["id"], experiment["id"])
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
    assert client.get(f"/api/exports/{export['id']}/download").status_code == 410


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
    never exported could be deleted."""
    monkeypatch.setattr(exports, "MIN_FREE_BYTES", 0)  # not the test machine's free space
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped()
    client = TestClient(app)
    started = client.post(f"/api/experiments/{experiment['id']}/export", json={"data": True, "photos": False})
    for _ in range(100):
        if database.get_export(started.json()["id"])["finished_at"]:
            break
        time.sleep(0.05)
    refused = client.post(f"/api/experiments/{experiment['id']}/purge", json={"confirm": "Drought"})
    assert refused.status_code == 409
    assert "no complete export" in refused.json()["detail"]
