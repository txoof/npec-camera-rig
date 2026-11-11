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


def _client():
    from fastapi.testclient import TestClient

    from npec_rig.app import app

    return TestClient(app)


def _unzipped(experiment_id: int, choice: dict | None = None) -> tuple[dict, dict[str, bytes]]:
    """Export through the page's route, download every part and unzip them into one folder, as
    the README says: the export with its parts, and every file by its name in that folder."""
    client = _client()
    started = client.post(f"/api/experiments/{experiment_id}/export", json=choice)
    assert started.status_code == 200, started.text
    export = started.json()
    files: dict[str, bytes] = {}
    for part in export["parts"]:
        with zipfile.ZipFile(io.BytesIO(client.get(f"/api/exports/{export['id']}/parts/{part['n']}").content)) as zf:
            for name in zf.namelist():
                files[name.split("/", 1)[1]] = zf.read(name)
    return export, files


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
    export, _files = _unzipped(experiment["id"], {"data": True, "photos": False})
    _array, after = captures.take_photo("capture")
    del _array
    # Downloaded after the next photo: the export still stops at its own time.
    files = {}
    for n in (0,):
        with zipfile.ZipFile(io.BytesIO(_client().get(f"/api/exports/{export['id']}/parts/{n}").content)) as zf:
            files.update({name.split("/", 1)[1]: zf.read(name) for name in zf.namelist()})
    rows = list(csv.DictReader(io.StringIO(files["captures.csv"].decode())))
    readme = files["README.txt"].decode()
    assert [r["path"] for r in rows] == [before["path"]]
    assert readme.startswith(f"PARTIAL EXPORT: photos up to {export['started_at']}")
    assert "still running" in readme


def test_one_export_at_a_time_per_experiment() -> None:
    experiment = _stopped_experiment_with_photos(0)
    database.create_export(experiment["id"], now="t")
    with pytest.raises(ExperimentError, match="already being prepared"):
        database.create_export(experiment["id"], now="t")


def test_the_parts_hold_everything_and_each_manifest_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    _calibrated_with_validation(monkeypatch)
    experiment = _stopped_experiment_with_photos(2)
    export, files = _unzipped(experiment["id"])
    inside = set(files)
    assert {"experiment.json", "captures.csv", "README.txt", "MANIFEST-part00.sha256"} <= inside
    assert f"records/calibrations/{_STEM}.json" in inside
    assert f"records/validations/{_SESSION}.json" in inside
    assert len([n for n in inside if n.startswith("stills/") and n.endswith(".jpg")]) == 2

    manifests = sorted(n for n in inside if n.startswith("MANIFEST-part"))
    assert manifests == [f"MANIFEST-part{p['n']:02d}.sha256" for p in export["parts"]]
    listed = {}
    for manifest in manifests:
        listed.update(dict(line.split("  ")[::-1] for line in files[manifest].decode().splitlines()))
    assert set(listed) == inside - set(manifests)
    for name, digest in listed.items():
        assert hashlib.sha256(files[name]).hexdigest() == digest

    rows = list(csv.DictReader(io.StringIO(files["captures.csv"].decode())))
    assert len(rows) == 2
    assert rows[0]["file"] in inside
    assert rows[0]["calibration"] == _STEM
    assert rows[0]["validation"] == _SESSION


def test_an_export_cut_off_by_a_restart_is_marked_failed() -> None:
    experiment = _stopped_experiment_with_photos(0)
    export = database.create_export(experiment["id"], now="t")
    assert database.fail_unfinished_exports(now="t2") == 1
    assert database.get_export(export["id"])["error"].startswith("the app restarted")


def test_export_and_download_through_the_page_routes() -> None:
    experiment = _stopped_experiment_with_photos(1)
    client = _client()
    started = client.post(f"/api/experiments/{experiment['id']}/export")
    assert started.status_code == 200
    export = started.json()
    assert export["finished_at"] is not None and export["error"] is None
    listed = {e["id"]: e for e in client.get("/api/experiments").json()}
    assert listed[experiment["id"]]["export"]["id"] == export["id"]
    assert client.get(f"/api/exports/{export['id']}").json()["parts"] == export["parts"]

    download = client.get(f"/api/exports/{export['id']}/parts/1")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert zipfile.ZipFile(io.BytesIO(download.content)).testzip() is None
    assert client.get(f"/api/exports/{export['id']}/parts/9").status_code == 404
    assert client.get("/api/exports/999/parts/0").status_code == 404


def test_the_export_name_starts_with_the_experiment_name() -> None:
    assert exports.slugify("A. thaliana Flash Drought!") == "a-thaliana-flash-drought"
    assert exports.slugify("Trockenstress Pflanzen über Nacht") == "trockenstress-pflanzen-uber-nacht"
    assert exports.slugify(None) == ""
    assert exports.slugify("x" * 60) == "x" * 40

    experiment = _stopped_experiment_with_photos(0)
    export = _client().post(f"/api/experiments/{experiment['id']}/export").json()
    part = _client().get(f"/api/exports/{export['id']}/parts/0")
    assert f'filename="drought_{experiment["folder"]}_export_' in part.headers["content-disposition"]
    assert part.headers["content-disposition"].endswith('_part00.zip"')


def test_an_unnamed_experiment_exports_under_its_folder_name() -> None:
    experiment = captures.start_experiment(captures.create_experiment()["id"])
    experiment = captures.stop_experiment(experiment["id"])
    export = _client().post(f"/api/experiments/{experiment['id']}/export").json()
    part = _client().get(f"/api/exports/{export['id']}/parts/0")
    assert f'filename="{experiment["folder"]}_export_' in part.headers["content-disposition"]


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
    _export, files = _unzipped(experiment["id"])
    rows = list(csv.reader(io.StringIO(files["time-in-table-location.csv"].decode())))
    readme = files["README.txt"].decode()
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

    _export, files = _unzipped(experiment["id"])
    rows = {r["path"]: r for r in csv.DictReader(io.StringIO(files["captures.csv"].decode()))}

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
    _export, files = _unzipped(experiment["id"])
    rows = list(csv.DictReader(io.StringIO(files["tray-readings.csv"].decode())))
    readme = files["README.txt"].decode()
    manifest = files["MANIFEST-part00.sha256"].decode()
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


def test_the_export_holds_each_trays_area_by_grow_from_leaf_cores_beside_the_fixed_cutoff() -> None:
    """#363 part 2: tray-readings.csv carries grow from leaf cores as stored (area, method with its
    core cutoff, the tray's soil level and lower cutoff) beside the fixed green cutoff's area,
    which is unchanged; a photo read before grow from leaf cores existed has those columns empty."""
    from datetime import UTC, datetime

    from tests.helpers import table_calibration, table_photo

    table_calibration()
    experiment = captures.start_experiment(captures.create_experiment(name="Cores")["id"])
    both = table_photo(experiment["id"], datetime(2026, 10, 2, tzinfo=UTC), {3: "NW"}, areas={3: 900.0})
    table_photo(experiment["id"], datetime(2026, 10, 2, 0, 1, tzinfo=UTC), {3: "NW"}, areas={3: 910.0})
    capture_id = database.captures_by_path([both])[both]["id"]
    [tray] = database.tray_readings(capture_id)["trays"]
    tray.update({"grown_method": "grow from leaf cores, core 0.07", "grown_area_mm2": 1156.0,
                 "grown_plant_px": 115600, "grown_plant_centre_px": [10.0, 20.0],
                 "grown_soil_level": -0.034999999999999578, "grown_lower_cutoff": 0.03500000000000043})
    database.record_tray_readings(capture_id, read_at="t", status="read", trays=[tray])
    captures.stop_experiment(experiment["id"])

    _export, files = _unzipped(experiment["id"])
    rows = list(csv.DictReader(io.StringIO(files["tray-readings.csv"].decode())))
    picked = [(r["plant_area_mm2"], r["cores_plant_area_mm2"], r["cores_method"], r["cores_soil_level"],
               r["cores_lower_cutoff"]) for r in rows]
    assert picked == [
        ("900.0", "1156.0", "grow from leaf cores, core 0.07", "-0.035", "0.035"),
        ("910.0", "", "", "", ""),
    ]


def test_the_export_holds_each_cells_area_and_status_by_grow_from_leaf_cores() -> None:
    """#363 part 2: cell-readings.csv carries each cell's status and area by grow from leaf cores
    beside the fixed green cutoff's; no area when it has none, never 0; a photo read before grow
    from leaf cores existed has those columns empty."""
    from datetime import UTC, datetime

    from tests.helpers import table_calibration, table_photo

    table_calibration()
    experiment = captures.start_experiment(captures.create_experiment(name="Cores cells")["id"])
    both = table_photo(experiment["id"], datetime(2026, 10, 2, tzinfo=UTC), {3: "NW"}, areas={3: 900.0})
    older = table_photo(experiment["id"], datetime(2026, 10, 2, 0, 1, tzinfo=UTC), {3: "NW"}, areas={3: 910.0})

    def cell(name, holds, px, area, grown_px, grown_area, grown_over):
        return {"cell": name, "holds": holds, "centre_px": [0.0, 0.0], "corners_px": [[0, 0]] * 4, "plant_px": px,
                "area_mm2": area, "plant_centre_px": None, "over_other_cells": False,
                "segmenter": "green threshold, 0.1", "cell_rule": "rule", "grown_plant_px": grown_px,
                "grown_area_mm2": grown_area, "grown_plant_centre_px": None, "grown_over_other_cells": grown_over}

    for path, cells in (
        (both, [cell("A1", "tag", 0, 0.0, 0, 0.0, False), cell("B1", "plant", 1205, 120.5, 1802, 180.2, False),
                cell("B2", "plant", 0, 0.0, 0, 0.0, False), cell("C1", "plant", 300, 30.0, 900, 90.0, True)]),
        (older, [cell("B1", "plant", 1210, 121.0, None, None, None)]),
    ):
        capture_id = database.captures_by_path([path])[path]["id"]
        [tray] = database.tray_readings(capture_id)["trays"]
        tray["cells"] = cells
        database.record_tray_readings(capture_id, read_at="t", status="read", trays=[tray])
    captures.stop_experiment(experiment["id"])

    _export, files = _unzipped(experiment["id"])
    rows = list(csv.DictReader(io.StringIO(files["cell-readings.csv"].decode())))
    picked = [(r["cell"], r["status"], r["plant_area_mm2"], r["cores_status"], r["cores_plant_area_mm2"]) for r in rows]
    assert picked == [
        ("A1", "tag", "", "tag", ""),
        ("B1", "plant", "120.5", "plant", "180.2"),
        ("B2", "missing", "", "missing", ""),
        ("C1", "plant", "30.0", "leaves over other cells", "90.0"),
        ("B1", "plant", "121.0", "", ""),
    ]


def test_an_export_with_nothing_ticked_is_refused() -> None:
    """#65, #368 item 2: the user ticks what goes in the export; with no box ticked there is
    nothing to export, and no export is recorded."""
    experiment = _stopped_experiment_with_photos(1)
    refused = _client().post(f"/api/experiments/{experiment['id']}/export", json={"data": False, "photos": False})
    assert refused.status_code == 422
    assert database.exports_for(experiment["id"]) == []


def _exported_names(experiment_id: int, choice: dict) -> set[str]:
    """The files in the export made through the page's route, every part unzipped into one folder."""
    return set(_unzipped(experiment_id, choice)[1])


def test_a_data_only_export_holds_the_data_and_no_photos() -> None:
    """#368 item 2: the data is experiment.json, the CSVs, the records, README and manifest."""
    experiment = _stopped_experiment_with_photos(2)
    names = _exported_names(experiment["id"], {"data": True, "photos": False})
    assert not [n for n in names if n.startswith("stills/")]
    assert {"experiment.json", "captures.csv", "time-in-table-location.csv", "tray-readings.csv",
            "README.txt", "MANIFEST-part00.sha256"} <= names


def test_a_photos_only_export_holds_the_photos_and_no_data() -> None:
    experiment = _stopped_experiment_with_photos(2)
    names = _exported_names(experiment["id"], {"data": False, "photos": True})
    assert len([n for n in names if n.startswith("stills/") and n.endswith(".jpg")]) == 2
    assert not [n for n in names if n.endswith(".csv") or n == "experiment.json"]
    assert {"README.txt", "MANIFEST-part00.sha256", "MANIFEST-part01.sha256"} <= names


def _exported_zip(experiment_id: int, choice: dict) -> dict[str, bytes]:
    """Every file in the export made through the page's route, every part unzipped into one folder."""
    return _unzipped(experiment_id, choice)[1]


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


def test_the_unused_light_norm_columns_are_never_exported() -> None:
    """#382: the exclusion table's norm_e and limit_fraction belong to the light norm of 17.8,
    dropped; they stay empty in rig.db until #384 removes them, and no exported file names them."""
    experiment = _stopped_experiment_with_photos(1)
    files = _exported_zip(experiment["id"], {"data": True, "photos": False})
    for name in sorted(n for n in files if n.endswith(".csv")):
        header = next(csv.reader(io.StringIO(files[name].decode())))
        assert not {"norm_e", "limit_fraction"} & set(header), name
    for name in ("datapackage.json", "README.txt"):
        assert "norm_e" not in files[name].decode() and "limit_fraction" not in files[name].decode(), name


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
    for choice, key, parts in (({"data": True, "photos": False}, "data_bytes", [0]),
                               ({"data": False, "photos": True}, "photos_bytes", None)):
        # The size of the download, the zips as they come down: the CSVs in part 0 are compressed
        # about 8 times (export 4 on npec-rig-01, 2026-11-06: 6.2 MB of files, a 756 kB zip).
        export = client.post(f"/api/experiments/{experiment['id']}/export", json=choice).json()
        numbers = parts if parts is not None else [p["n"] for p in export["parts"] if p["n"] >= 1]
        made = sum(len(client.get(f"/api/exports/{export['id']}/parts/{n}").content) for n in numbers)
        assert made / 3 <= expected[key] <= made * 3, (key, expected[key], made)


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
    _export, files = _unzipped(experiment["id"])
    rows = list(csv.DictReader(io.StringIO(files["cell-readings.csv"].decode())))
    readme = files["README.txt"].decode()
    manifest = files["MANIFEST-part00.sha256"].decode()
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


# --- The export in parts, each zipped while it downloads (#368) ---


def _photo_bytes(experiment: dict) -> list[int]:
    """Each photo's size with its record, oldest first, read from the experiment's folder."""
    from npec_rig.captures import experiments_root

    sizes = []
    for row in database.captures_for_experiment(experiment["id"]):
        stem = experiments_root() / row["path"].removeprefix("experiments/")
        sizes.append(sum(p.stat().st_size for p in (stem.with_suffix(".jpg"), stem.with_suffix(".json")) if p.exists()))
    return sizes


def test_an_export_lists_its_parts_each_under_the_part_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """B1: part 0 holds the README and the data; every photo is in one photo part, and a part
    holds no more than PART_BYTES of photos (set here to about two photos)."""
    experiment = _stopped_experiment_with_photos(5)
    sizes = _photo_bytes(experiment)
    monkeypatch.setattr(exports, "PART_BYTES", 2 * max(sizes))
    export = _client().post(f"/api/experiments/{experiment['id']}/export", json={"data": True, "photos": True}).json()
    parts = export["parts"]
    assert [p["n"] for p in parts] == list(range(len(parts)))
    assert parts[0]["photos"] == 0
    photo_parts = parts[1:]
    assert len(photo_parts) == 3
    assert sum(p["photos"] for p in photo_parts) == 5
    assert all(p["bytes"] <= 2 * max(sizes) * 1.01 + 10_000 for p in photo_parts)


def test_each_part_announces_its_exact_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """B2: the browser shows progress from Content-Length (Aaron tried Chrome and Firefox,
    2026-11-06), so it must equal what is sent, and the parts list gives the same size."""
    experiment = _stopped_experiment_with_photos(3)
    monkeypatch.setattr(exports, "PART_BYTES", max(_photo_bytes(experiment)))
    client = _client()
    export = client.post(f"/api/experiments/{experiment['id']}/export").json()
    for part in export["parts"]:
        got = client.get(f"/api/exports/{export['id']}/parts/{part['n']}")
        assert int(got.headers["content-length"]) == len(got.content), part["n"]
        if part["n"] >= 1:
            assert part["bytes"] == len(got.content)


def test_a_running_experiments_parts_stay_the_same_as_photos_come(monkeypatch: pytest.MonkeyPatch) -> None:
    """B3: the parts hold the photos up to the export's time, however many come after, so a part
    downloaded later is the same part."""
    experiment = captures.start_experiment(captures.create_experiment(name="Drought")["id"])
    for _ in range(2):
        _array, _record = captures.take_photo("capture")
    monkeypatch.setattr(exports, "PART_BYTES", max(_photo_bytes(experiment)))
    client = _client()
    export = client.post(f"/api/experiments/{experiment['id']}/export").json()
    first = client.get(f"/api/exports/{export['id']}/parts/2").content
    for _ in range(3):
        _array, _record = captures.take_photo("capture")
    del _array
    again = client.get(f"/api/exports/{export['id']}")
    assert again.json()["parts"][2]["bytes"] == export["parts"][2]["bytes"]
    assert len(again.json()["parts"]) == 3
    later = client.get(f"/api/exports/{export['id']}/parts/2").content
    assert zipfile.ZipFile(io.BytesIO(later)).namelist() == zipfile.ZipFile(io.BytesIO(first)).namelist()


def test_purge_needs_every_photo_part_sent_in_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """B4: an export in parts is complete only when every photo part was sent to its last byte; a
    download broken off part way does not count."""
    experiment = _stopped_experiment_with_photos(2)
    monkeypatch.setattr(exports, "PART_BYTES", max(_photo_bytes(experiment)))
    client = _client()
    export = client.post(f"/api/experiments/{experiment['id']}/export").json()
    assert [p["n"] for p in export["parts"]] == [0, 1, 2]
    client.get(f"/api/exports/{export['id']}/parts/1")
    _name, _length, body = exports.part_download(export["id"], 2)
    next(body)
    body.close()  # broken off after the first piece
    assert database.complete_export(experiment["id"]) is None
    assert [p["sent"] for p in client.get(f"/api/exports/{export['id']}").json()["parts"]] == [False, True, False]
    client.get(f"/api/exports/{export['id']}/parts/2")
    assert database.complete_export(experiment["id"])["id"] == export["id"]


def test_the_export_says_from_when_a_trays_cell_names_may_be_swapped() -> None:
    """#385: a tray whose tag turned on it has its cell names marked as maybe swapped from that
    photo on; the cell lines carry the time of that photo, empty before it."""
    from datetime import UTC, datetime

    from tests.helpers import table_calibration, table_photo

    table_calibration()
    experiment = captures.start_experiment(captures.create_experiment(name="Turned")["id"])
    paths = [table_photo(experiment["id"], datetime(2026, 11, day, tzinfo=UTC), {3: "NW"}, areas={3: 100.0})
             for day in (3, 4)]
    for path, turned in zip(paths, (False, True), strict=True):
        capture_id = database.captures_by_path([path])[path]["id"]
        [tray] = database.tray_readings(capture_id)["trays"]
        tray["warnings"] = ["tag turned on tray"] if turned else []
        tray["cells"] = [{"cell": "A1", "holds": "plant", "centre_px": [0.0, 0.0], "corners_px": [[0, 0]] * 4,
                          "plant_px": 100, "area_mm2": 10.0, "plant_centre_px": None, "over_other_cells": False,
                          "segmenter": "green threshold, 0.1", "cell_rule": "rule"}]
        database.record_tray_readings(capture_id, read_at="t", status="read", trays=[tray])
    captures.stop_experiment(experiment["id"])
    _export, files = _unzipped(experiment["id"])
    rows = list(csv.DictReader(io.StringIO(files["cell-readings.csv"].decode())))
    second = database.captures_by_path([paths[1]])[paths[1]]["taken_at"]
    assert [(r["taken_at"][:10], r["names_unsure_since"]) for r in rows] == [("2026-11-03", ""), ("2026-11-04", second)]
