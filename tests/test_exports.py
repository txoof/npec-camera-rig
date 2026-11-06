import csv
import hashlib
import io
import time
import zipfile

import pytest

from npec_rig import captures, database, exports
from npec_rig.database import ExperimentError
from tests.helpers import stored_validation

pytestmark = pytest.mark.unit

_STEM = "20261009T073108292325"
_SESSION = "20261009T100000000000"


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))
    # No fixed reserve, so these tests do not depend on the free space of the test machine.
    monkeypatch.setattr(exports, "MIN_FREE_BYTES", 0)


def _calibrated_with_validation(monkeypatch: pytest.MonkeyPatch) -> None:
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
    stored_validation(_SESSION, _STEM)
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


def test_an_experiment_that_never_started_has_nothing_to_export() -> None:
    set_up = captures.create_experiment()
    with pytest.raises(ExperimentError, match="has not started"):
        database.create_export(set_up["id"], now="t")


def test_a_running_experiment_exports_its_photos_so_far() -> None:
    experiment = captures.start_experiment(captures.create_experiment(name="Drought")["id"])
    _array, before = captures.take_photo("capture")
    export = database.create_export(experiment["id"], now=exports._now())
    _array, after = captures.take_photo("capture")
    del _array
    exports._build(export["id"], experiment["id"])

    export = database.get_export(export["id"])
    assert export["error"] is None
    with zipfile.ZipFile(exports.zip_path(export)) as zf:
        top = zf.namelist()[0].split("/")[0]
        rows = list(csv.DictReader(io.StringIO(zf.read(f"{top}/captures.csv").decode())))
        readme = zf.read(f"{top}/README.txt").decode()
    assert [r["path"] for r in rows] == [before["path"]]
    assert readme.startswith(f"PARTIAL EXPORT: photos up to {export['started_at']}")
    assert "still running" in readme


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


def test_the_export_holds_each_trays_hours_in_each_table_location() -> None:
    """#332, hand-worked: tray 7 in NW from 1 October 00:00 to 3 October 00:00 (48 h), then in SE
    from 00:01 to 06:01 (6 h). Tray 8 in SW for the same 48 h; its 3 minutes in NM is a nudge, so
    its SW stay runs to its last photo there, 00:04 (48 h 4 min)."""
    from datetime import UTC, datetime

    from tests.helpers import table_calibration, table_photo

    table_calibration()
    experiment = captures.start_experiment(captures.create_experiment(name="Dwell")["id"])
    for when, trays in [
        ((1, 0, 0), {7: "NW", 8: "SW"}), ((3, 0, 0), {7: "NW", 8: "SW"}), ((3, 0, 1), {7: "SE", 8: "NM"}),
        ((3, 0, 4), {8: "SW"}), ((3, 6, 1), {7: "SE"}),
    ]:
        table_photo(experiment["id"], datetime(2026, 10, *when, tzinfo=UTC), trays)
    captures.stop_experiment(experiment["id"])
    export = database.create_export(experiment["id"], now=exports._now())
    exports._build(export["id"], experiment["id"])

    with zipfile.ZipFile(exports.zip_path(database.get_export(export["id"]))) as zf:
        top = zf.namelist()[0].split("/")[0]
        rows = list(csv.reader(io.StringIO(zf.read(f"{top}/time-in-table-location.csv").decode())))
        readme = zf.read(f"{top}/README.txt").decode()
    assert rows == [
        ["tray", "NW_h", "NM_h", "NE_h", "SW_h", "SM_h", "SE_h"],
        ["7", "48.00", "0.00", "0.00", "0.00", "0.00", "6.00"],
        ["8", "0.00", "0.00", "0.00", "48.07", "0.00", "0.00"],
    ]
    assert "time-in-table-location.csv" in readme


def test_captures_csv_says_which_photos_were_taken_before_the_clock_had_the_network_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(captures, "CLOCK_SYNC_MARKER", tmp_path / "synchronized")  # not there
    experiment = captures.start_experiment(captures.create_experiment(name="Power cut")["id"])
    _array, unset = captures.take_photo("capture")
    (tmp_path / "synchronized").touch()
    _array, synced = captures.take_photo("capture")
    del _array
    captures.stop_experiment(experiment["id"])

    export = exports.start_export(experiment["id"])
    for _ in range(100):
        export = database.get_export(export["id"])
        if export["finished_at"]:
            break
        time.sleep(0.05)
    assert export["error"] is None
    with zipfile.ZipFile(exports.zip_path(export)) as zf:
        top = zf.namelist()[0].split("/")[0]
        rows = {r["path"]: r for r in csv.DictReader(io.StringIO(zf.read(f"{top}/captures.csv").decode()))}

    assert rows[unset["path"]]["clock_synced"] == "0"
    assert rows[synced["path"]]["clock_synced"] == "1"


def test_the_export_holds_each_trays_plant_area_with_its_slots_validation_band() -> None:
    """#76: tray 3 lies in NW, nearest North 1 (±2.0 %); tray 7 in SE, nearest South 6, whose 9
    tags are too few to measure (tests/helpers.banded_validation). The second photo has no
    validation; the third is flagged as not covered by the bands. Areas as stored."""
    from datetime import UTC, datetime

    from tests.helpers import banded_validation, table_calibration, table_photo

    table_calibration()
    banded_validation("20261001T000000000000", {"North 1": ((150, 150), 2.0), "South 6": ((750, 450), None)})
    experiment = captures.start_experiment(captures.create_experiment(name="Bands")["id"])
    first = table_photo(experiment["id"], datetime(2026, 10, 2, tzinfo=UTC), {3: "NW", 7: "SE"},
                        validation="20261001T000000000000", areas={3: 1234.5, 7: 980.0})
    second = table_photo(experiment["id"], datetime(2026, 10, 2, 0, 1, tzinfo=UTC), {3: "NW"}, areas={3: 1240.0})
    table_photo(experiment["id"], datetime(2026, 10, 2, 0, 2, tzinfo=UTC), {3: "NW"}, areas={3: 1250.0},
                validation="20261001T000000000000", flags=["lens moved from its lock"])
    captures.stop_experiment(experiment["id"])
    export = database.create_export(experiment["id"], now=exports._now())
    exports._build(export["id"], experiment["id"])

    with zipfile.ZipFile(exports.zip_path(database.get_export(export["id"]))) as zf:
        top = zf.namelist()[0].split("/")[0]
        rows = list(csv.DictReader(io.StringIO(zf.read(f"{top}/tray-readings.csv").decode())))
        readme = zf.read(f"{top}/README.txt").decode()
        manifest = zf.read(f"{top}/MANIFEST.sha256").decode()
    picked = [(r["taken_at"], r["tray"], r["location"], r["plant_area_mm2"], r["scale_error_at_tray_top_pct"],
               r["band_slot"], r["no_band_reason"]) for r in rows]
    assert picked == [
        ("2026-10-02T00:00:00+00:00", "3", "NW", "1234.5", "2.0", "North 1", ""),
        ("2026-10-02T00:00:00+00:00", "7", "SE", "980.0", "", "South 6", "slot not measured"),
        ("2026-10-02T00:01:00+00:00", "3", "NW", "1240.0", "", "", "not validated"),
        ("2026-10-02T00:02:00+00:00", "3", "NW", "1250.0", "", "", "photo not covered"),
    ]
    assert [r["file"] for r in rows][:3] == [f"stills/{first.split('/stills/')[-1]}.jpg"] * 2 + [
        f"stills/{second.split('/stills/')[-1]}.jpg"]
    assert "tray-readings.csv" in readme
    assert "  tray-readings.csv\n" in manifest


def _client():
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    return TestClient(app)


def _finished(export_id: int) -> dict:
    for _ in range(100):
        export = database.get_export(export_id)
        if export["finished_at"]:
            return export
        time.sleep(0.05)
    raise AssertionError("the export did not finish")


def test_an_export_with_nothing_ticked_is_refused() -> None:
    """#65, #368 item 2: the user ticks what goes in the export; with no box ticked there is
    nothing to export, and no export is recorded."""
    experiment = _stopped_experiment_with_photos(1)
    refused = _client().post(f"/api/experiments/{experiment['id']}/export", json={"data": False, "photos": False})
    assert refused.status_code == 422
    assert database.exports_for(experiment["id"]) == []


def _exported_names(experiment_id: int, choice: dict) -> set[str]:
    """The files in the export made through the page's route, without the top folder."""
    client = _client()
    started = client.post(f"/api/experiments/{experiment_id}/export", json=choice)
    assert started.status_code == 200
    export = _finished(started.json()["id"])
    assert export["error"] is None
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/exports/{export['id']}/download").content)) as zf:
        return {n.split("/", 1)[1] for n in zf.namelist()}


def test_a_data_only_export_holds_the_data_and_no_photos() -> None:
    """#368 item 2: the data is experiment.json, the CSVs, the records, README and manifest."""
    experiment = _stopped_experiment_with_photos(2)
    names = _exported_names(experiment["id"], {"data": True, "photos": False})
    assert not [n for n in names if n.startswith("stills/")]
    assert {"experiment.json", "captures.csv", "time-in-table-location.csv", "tray-readings.csv",
            "README.txt", "MANIFEST.sha256"} <= names


def test_a_photos_only_export_holds_the_photos_and_no_data() -> None:
    experiment = _stopped_experiment_with_photos(2)
    names = _exported_names(experiment["id"], {"data": False, "photos": True})
    assert len([n for n in names if n.startswith("stills/") and n.endswith(".jpg")]) == 2
    assert not [n for n in names if n.endswith(".csv") or n == "experiment.json"]
    assert {"README.txt", "MANIFEST.sha256"} <= names


def _exported_zip(experiment_id: int, choice: dict) -> dict[str, bytes]:
    """Every file in the export made through the page's route, by its name without the top folder."""
    client = _client()
    started = client.post(f"/api/experiments/{experiment_id}/export", json=choice)
    export = _finished(started.json()["id"])
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/exports/{export['id']}/download").content)) as zf:
        return {n.split("/", 1)[1]: zf.read(n) for n in zf.namelist()}


def test_every_csv_column_is_described_in_the_data_package() -> None:
    """#65: a Frictionless Data Package (datapackage.json) names each CSV with its columns in
    order, each with a type and a description, so the data needs no other document."""
    import json

    experiment = _stopped_experiment_with_photos(1)
    files = _exported_zip(experiment["id"], {"data": True, "photos": False})
    package = json.loads(files["datapackage.json"])
    resources = {r["path"]: r for r in package["resources"]}
    csvs = sorted(n for n in files if n.endswith(".csv"))
    assert csvs == ["captures.csv", "cell-readings.csv", "time-in-table-location.csv", "tray-readings.csv"]
    for name in csvs:
        header = next(csv.reader(io.StringIO(files[name].decode())))
        fields = resources[name]["schema"]["fields"]
        assert [f["name"] for f in fields] == header, name
        assert all(f["type"] and f["description"].strip() for f in fields), name
        assert resources[name]["description"].strip()


def test_the_readme_explains_every_column_from_the_data_package() -> None:
    """#65: the README alone explains the data. Each CSV, each of its columns and the column's
    description from datapackage.json are in it (whitespace aside: the README wraps lines)."""
    import json

    experiment = _stopped_experiment_with_photos(1)
    files = _exported_zip(experiment["id"], {"data": True, "photos": False})
    readme = " ".join(files["README.txt"].decode().split())
    for resource in json.loads(files["datapackage.json"])["resources"]:
        assert resource["path"] in readme
        for field in resource["schema"]["fields"]:
            assert f"{field['name']}: {' '.join(field['description'].split())}" in readme, field["name"]


def test_the_expected_sizes_are_the_right_order_of_magnitude() -> None:
    """#65: before exporting, the dialog shows how large the data and the photos will be, so the
    user knows whether it takes minutes or hours. An order of magnitude is enough (Aaron,
    2026-11-06): each estimate within a factor of 3 of the export actually made."""
    experiment = _stopped_experiment_with_photos(3)
    client = _client()
    expected = client.get(f"/api/experiments/{experiment['id']}/export-size").json()
    for choice, key in (({"data": True, "photos": False}, "data_bytes"), ({"data": False, "photos": True}, "photos_bytes")):
        # The size of the download, the zip as it comes down: the CSVs in it are compressed
        # about 8 times (export 4 on npec-rig-01, 2026-11-06: 6.2 MB of files, a 756 kB zip).
        started = client.post(f"/api/experiments/{experiment['id']}/export", json=choice)
        export = _finished(started.json()["id"])
        made = len(client.get(f"/api/exports/{export['id']}/download").content)
        assert made / 3 <= expected[key] <= made * 3, (key, expected[key], made)


def test_an_export_that_would_leave_too_little_free_space_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """#65 (Aaron, 2026-11-06): a full export on the development rig nearly filled the disk under
    a running experiment. The fixed reserve is raised past any disk here, so nothing fits."""
    experiment = _stopped_experiment_with_photos(1)
    monkeypatch.setattr(exports, "MIN_FREE_BYTES", 10**18)
    refused = _client().post(f"/api/experiments/{experiment['id']}/export", json={"data": True, "photos": True})
    assert refused.status_code == 409
    assert "disk space" in refused.json()["detail"]
    assert database.exports_for(experiment["id"]) == []


def test_the_running_experiments_next_photos_are_kept_room_for(monkeypatch: pytest.MonkeyPatch) -> None:
    """#65: the space kept free covers COVER_DAYS of the running experiment's photos at its
    interval and its photos' size. With no fixed reserve, only that cover can refuse the export;
    raised to a span no disk holds, it does, even for the small data."""
    experiment = captures.create_experiment(name="Drought", interval_s=60)
    experiment = captures.start_experiment(experiment["id"])
    _array, _record = captures.take_photo("capture")
    del _array
    monkeypatch.setattr(exports, "MIN_FREE_BYTES", 0)
    client = _client()
    choice = {"data": True, "photos": False}
    monkeypatch.setattr(exports, "COVER_DAYS", 10**9)
    refused = client.post(f"/api/experiments/{experiment['id']}/export", json=choice)
    assert refused.status_code == 409
    monkeypatch.setattr(exports, "COVER_DAYS", 0)
    assert client.post(f"/api/experiments/{experiment['id']}/export", json=choice).status_code == 200


def test_the_export_holds_each_cells_plant_area_or_the_word_for_why_it_has_none() -> None:
    """#364: one line per cell of each tray in each photo, for the researcher's own plant map
    (tray and cell to treatment). A missing cell and the tag's cell have no area, never 0."""
    from datetime import UTC, datetime

    from tests.helpers import banded_validation, table_calibration, table_photo

    table_calibration()
    banded_validation("20261001T000000000000", {"North 1": ((150, 150), 2.0)})
    experiment = captures.start_experiment(captures.create_experiment(name="Cells")["id"])
    path = table_photo(experiment["id"], datetime(2026, 10, 2, tzinfo=UTC), {3: "NW"},
                       validation="20261001T000000000000", areas={3: 1234.5})
    capture_id = database.captures_by_path([path])[path]["id"]
    [tray] = database.tray_readings(capture_id)["trays"]

    def cell(name, holds, px, area, over):
        return {"cell": name, "holds": holds, "centre_px": [0.0, 0.0], "corners_px": [[0, 0]] * 4, "plant_px": px,
                "area_mm2": area, "plant_centre_px": None, "over_other_cells": over,
                "segmenter": "green threshold, 0.1", "cell_rule": "rule"}

    tray["cells"] = [cell("A1", "tag", 0, 0.0, False), cell("B1", "plant", 1205, 120.5, False),
                     cell("B2", "plant", 0, 0.0, False), cell("C1", "plant", 300, 30.0, True)]
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[tray])
    captures.stop_experiment(experiment["id"])
    export = database.create_export(experiment["id"], now=exports._now())
    exports._build(export["id"], experiment["id"])

    with zipfile.ZipFile(exports.zip_path(database.get_export(export["id"]))) as zf:
        top = zf.namelist()[0].split("/")[0]
        rows = list(csv.DictReader(io.StringIO(zf.read(f"{top}/cell-readings.csv").decode())))
        readme = zf.read(f"{top}/README.txt").decode()
        manifest = zf.read(f"{top}/MANIFEST.sha256").decode()
    picked = [(r["tray"], r["location"], r["cell"], r["status"], r["plant_area_mm2"], r["band_slot"]) for r in rows]
    assert picked == [
        ("3", "NW", "A1", "tag", "", "North 1"),
        ("3", "NW", "B1", "plant", "120.5", "North 1"),
        ("3", "NW", "B2", "missing", "", "North 1"),
        ("3", "NW", "C1", "leaves over other cells", "30.0", "North 1"),
    ]
    assert {r["file"] for r in rows} == {f"stills/{path.split('/stills/')[-1]}.jpg"}
    assert {r["cell_rule"] for r in rows} == {"rule"}
    assert "cell-readings.csv" in readme
    assert "  cell-readings.csv\n" in manifest


def test_the_dialog_is_told_beforehand_how_much_an_export_may_take(monkeypatch: pytest.MonkeyPatch) -> None:
    """#65 (Aaron, 2026-11-06): only the choice that would leave the disk too full is stopped, and
    the dialog says so before the tap: export-size gives the space an export may use, the free
    space less the reserve."""
    experiment = _stopped_experiment_with_photos(1)
    monkeypatch.setattr(exports, "MIN_FREE_BYTES", 10**18)
    sizes = _client().get(f"/api/experiments/{experiment['id']}/export-size").json()
    assert sizes["usable_bytes"] < sizes["photos_bytes"]
    monkeypatch.setattr(exports, "MIN_FREE_BYTES", 0)
    sizes = _client().get(f"/api/experiments/{experiment['id']}/export-size").json()
    assert sizes["usable_bytes"] > sizes["photos_bytes"] + sizes["data_bytes"]
