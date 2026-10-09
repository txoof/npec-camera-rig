import csv
import hashlib
import io
import time
import zipfile

import pytest

from npec_rig import captures, database, exports
from npec_rig.database import ExperimentError

pytestmark = pytest.mark.unit

_STEM = "20261009T073108292325"
_SESSION = "20261009T100000000000"


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _calibrated_with_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    from npec_rig import validation_store
    from npec_rig.calibration import CalibrationArtifact, ScaleField
    from npec_rig.calibration_store import save_calibration

    save_calibration(
        CalibrationArtifact(
            created_at="2026-10-09T07:31:08+00:00",
            scale_field=ScaleField(_coeffs=(1.0, 0.0, 0.0), _mean_px_per_mm=4.0, residual_std_pct=1.0),
            frame_stem=_STEM,
            lens_position=6.04,
        ),
        stem=_STEM,
    )
    validation_store.save_session(
        {"id": _SESSION, "calibration_stem": _STEM, "completed_at": "2026-10-09T11:00:00+00:00"}
    )
    monkeypatch.setattr(
        captures.CameraManager.instance(),
        "focus_status",
        lambda: {"locked": True, "lens_position": 6.04},
    )


def _stopped_experiment_with_photos(count: int = 2) -> dict:
    experiment = captures.start_experiment(captures.create_experiment(name="Drought")["id"])
    for _ in range(count):
        _array, _record = captures.take_photo("capture")
        del _array
    return captures.stop_experiment(experiment["id"])


def test_only_a_stopped_experiment_can_be_exported() -> None:
    set_up = captures.create_experiment()
    with pytest.raises(ExperimentError, match="only a stopped experiment"):
        database.create_export(set_up["id"], now="t")
    running = captures.start_experiment(set_up["id"])
    with pytest.raises(ExperimentError, match="only a stopped experiment"):
        database.create_export(running["id"], now="t")


def test_one_export_at_a_time_per_experiment() -> None:
    experiment = _stopped_experiment_with_photos(0)
    database.create_export(experiment["id"], now="t")
    with pytest.raises(ExperimentError, match="already being prepared"):
        database.create_export(experiment["id"], now="t")


def test_the_zip_holds_everything_and_the_manifest_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    _calibrated_with_validation(monkeypatch)
    experiment = _stopped_experiment_with_photos(2)
    export = database.create_export(experiment["id"], now="t")
    exports._build(export["id"], experiment["id"])

    export = database.get_export(export["id"])
    assert export["error"] is None
    path = exports.zip_path(export)
    assert path.exists()
    assert export["bytes"] == path.stat().st_size

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        top = names[0].split("/")[0]
        inside = {n.removeprefix(top + "/") for n in names}
        assert {"experiment.json", "captures.csv", "README.txt", "MANIFEST.sha256"} <= inside
        assert f"records/calibrations/{_STEM}.json" in inside
        assert f"records/validations/{_SESSION}.json" in inside
        assert len([n for n in inside if n.startswith("stills/") and n.endswith(".jpg")]) == 2

        manifest = zf.read(f"{top}/MANIFEST.sha256").decode()
        listed = dict(line.split("  ")[::-1] for line in manifest.splitlines())
        assert set(listed) == inside - {"MANIFEST.sha256"}
        for name, digest in listed.items():
            assert hashlib.sha256(zf.read(f"{top}/{name}")).hexdigest() == digest
        assert export["files"] == len(listed)
        assert export["manifest_sha256"] == hashlib.sha256(manifest.encode()).hexdigest()

        rows = list(csv.DictReader(io.StringIO(zf.read(f"{top}/captures.csv").decode())))
        assert len(rows) == 2
        assert rows[0]["file"] in inside
        assert rows[0]["calibration"] == _STEM
        assert rows[0]["validation"] == _SESSION


def test_a_failure_is_recorded_with_its_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    experiment = _stopped_experiment_with_photos(0)
    export = database.create_export(experiment["id"], now="t")

    def broken(*_args: object) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(exports, "_write_zip", broken)
    exports._build(export["id"], experiment["id"])
    export = database.get_export(export["id"])
    assert export["error"] == "No space left on device"
    assert export["finished_at"] is not None


def test_an_export_cut_off_by_a_restart_is_marked_failed() -> None:
    experiment = _stopped_experiment_with_photos(0)
    export = database.create_export(experiment["id"], now="t")
    assert database.fail_unfinished_exports(now="t2") == 1
    assert database.get_export(export["id"])["error"].startswith("the app restarted")


def test_export_and_download_through_the_page_routes() -> None:
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    experiment = _stopped_experiment_with_photos(1)
    client = TestClient(app)
    started = client.post(f"/api/experiments/{experiment['id']}/export")
    assert started.status_code == 200
    for _ in range(100):
        export = database.get_export(started.json()["id"])
        if export["finished_at"]:
            break
        time.sleep(0.05)
    assert export["error"] is None
    listed = {e["id"]: e for e in client.get("/api/experiments").json()}
    assert listed[experiment["id"]]["export"]["id"] == export["id"]

    download = client.get(f"/api/exports/{export['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(download.content)).testzip() is None
    assert client.get("/api/exports/999/download").status_code == 404


def test_the_export_name_starts_with_the_experiment_name() -> None:
    assert exports.slugify("A. thaliana Flash Drought!") == "a-thaliana-flash-drought"
    assert exports.slugify("Trockenstress Pflanzen über Nacht") == "trockenstress-pflanzen-uber-nacht"
    assert exports.slugify(None) == ""
    assert exports.slugify("x" * 60) == "x" * 40

    experiment = _stopped_experiment_with_photos(0)
    export = database.create_export(experiment["id"], now="t")
    exports._build(export["id"], experiment["id"])
    assert exports.zip_path(database.get_export(export["id"])).name.startswith(
        f"drought_{experiment['folder']}_export_"
    )


def test_an_unnamed_experiment_exports_under_its_folder_name() -> None:
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    experiment = captures.stop_experiment(experiment["id"])
    export = database.create_export(experiment["id"], now="t")
    exports._build(export["id"], experiment["id"])
    assert exports.zip_path(database.get_export(export["id"])).name.startswith(
        f"{experiment['folder']}_export_"
    )
