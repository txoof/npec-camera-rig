"""The About page (#390): what the rig runs and the state it is in.

Seams (Aaron, 2026-11-09): GET /api/about returns each fact against a known setup; GET /about
shows each section with those values; every page's rail links to /about."""

import pytest
from fastapi.testclient import TestClient

from npec_rig.app import app

pytestmark = pytest.mark.unit


def test_api_about_reports_the_focus_lock_and_lens_position():
    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    focus = client.get("/api/about").json()["focus"]

    assert focus == {"locked": True, "lens_position": 6.3}


def test_api_about_reports_the_calibration_and_validation_dates(isolated_calibration_dir):
    from tests.helpers import TABLE_STEM, stored_validation, table_calibration

    table_calibration()  # made 2027-01-01 00:00 UTC
    stored_validation("20270101T010000000000", TABLE_STEM)  # three rounds, complete an hour later

    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")  # a validation counts only under a locked focus

    body = client.get("/api/about").json()

    assert body["calibration"] == {"stem": TABLE_STEM, "created_at": "2027-01-01T00:00:00+00:00"}
    assert body["validation"]["state"] == "validated"
    assert body["validation"]["completed_at"] == "2027-01-01T02:00:00+00:00"


def test_api_about_reports_the_app_start_and_the_running_experiment():
    from npec_rig import database

    database.record_app_start("2027-01-02T08:00:00+00:00")
    database.record_app_start("2027-01-03T09:30:00+00:00")
    client = TestClient(app)
    made = client.post("/api/experiments", json={"name": "potato 3"}).json()
    started = client.post(f"/api/experiments/{made['id']}/start").json()

    body = client.get("/api/about").json()

    assert body["app_started_at"] == "2027-01-03T09:30:00+00:00"  # the latest start
    assert body["experiment"] == {
        "id": made["id"], "name": "potato 3", "started_at": started["periods"][-1]["started_at"],
    }


def test_api_about_reports_no_experiment_when_none_is_running():
    assert TestClient(app).get("/api/about").json()["experiment"] is None


def test_api_about_reports_the_software_and_the_rig(monkeypatch):
    import socket
    import subprocess
    from pathlib import Path

    import npec_rig
    from npec_rig import database

    monkeypatch.setenv("NPEC_RIG_ENVIRONMENT", "development")
    checkout = Path(npec_rig.__file__).parent
    commit = subprocess.run(["git", "-C", str(checkout), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True, check=True).stdout.strip()
    client = TestClient(app)

    body = client.get("/api/about").json()

    assert body["version"]["commit"] == commit
    assert body["schema_version"] == database.SCHEMA_VERSION
    assert body["rig"] == {"name": socket.gethostname(), "environment": "development"}
    camera = client.get("/camera/health").json()
    assert body["camera"] == {"state": camera["state"], "detail": camera["detail"]}
    assert 0 < body["disk"]["free_bytes"] <= body["disk"]["total_bytes"]
    assert body["pi_up_s"] > 0
    assert isinstance(body["ai_accelerator"], bool)


def test_about_page_shows_each_section_and_its_values(isolated_calibration_dir):
    import subprocess
    from pathlib import Path

    import npec_rig
    from tests.helpers import TABLE_STEM, stored_validation, table_calibration

    table_calibration()
    stored_validation("20270101T010000000000", TABLE_STEM)
    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")
    made = client.post("/api/experiments", json={"name": "potato 3"}).json()
    client.post(f"/api/experiments/{made['id']}/start")
    commit = subprocess.run(["git", "-C", str(Path(npec_rig.__file__).parent), "rev-parse", "--short",
                             "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

    page = client.get("/about")

    assert page.status_code == 200
    for title in ("Software", "Rig", "Running", "Focus", "Calibration and validation"):
        assert f">{title}</h3>" in page.text
    assert commit in page.text
    assert "Locked" in page.text and "6.30" in page.text
    assert 'datetime="2027-01-01T00:00:00+00:00"' in page.text  # calibration made
    assert 'datetime="2027-01-01T02:00:00+00:00"' in page.text  # validation completed
    assert "potato 3" in page.text


@pytest.mark.parametrize("path", ["/gallery", "/experiments", "/setup"])
def test_every_page_rail_links_to_about(path):
    page = TestClient(app).get(path).text
    rail = page[page.index('<nav class="rail"'):page.index("</nav>")]

    assert 'href="/about"' in rail


def test_about_page_names_the_camera_without_its_device_path():
    from npec_rig.camera import CameraManager, SyntheticBackend

    class Arducam(SyntheticBackend):  # the text npec-rig-01 reported on 2026-11-09
        OPENED_DETAIL = ("Camera attached and working (arducam_64mp "
                         "/base/axi/pcie@1000120000/rp1/i2c@88000/arducam_64mp@1a).")

    CameraManager.set_instance(CameraManager(Arducam()))
    client = TestClient(app)

    page = client.get("/about").text

    assert "Camera attached and working (arducam_64mp)." in page
    assert "/base/axi" not in page
    assert "/base/axi" in client.get("/api/about").json()["camera"]["detail"]  # scripts keep all of it


def test_about_page_says_validated_once(isolated_calibration_dir):
    from tests.helpers import TABLE_STEM, stored_validation, table_calibration

    table_calibration()
    stored_validation("20270101T010000000000", TABLE_STEM)
    client = TestClient(app)
    client.post("/controls/lens-position", json={"value": 6.3})
    client.post("/focus/lock")

    page = client.get("/about").text

    assert page.count("Validated") == 1  # the chip; the date is in "Validation finished"


def test_api_about_reports_days_of_disk_space_left(tmp_path):
    """#307: days left at the rate files were written in the data folder (a temporary folder in
    tests, where rig.db is)."""
    (tmp_path / "rig").mkdir()
    (tmp_path / "rig" / "photo.jpg").write_bytes(b"x" * 1000)
    disk = TestClient(app).get("/api/about").json()["disk"]
    assert disk["days_left"] > 0
    assert disk["level"] in ("ok", "yellow", "red")


def test_about_page_shows_days_of_disk_space_left(tmp_path):
    (tmp_path / "rig").mkdir()
    (tmp_path / "rig" / "photo.jpg").write_bytes(b"x" * 1000)
    page = TestClient(app).get("/about").text
    row = page[page.index("Disk space left"):][:600]
    assert "days at the last day" in row
    assert "Enough" in row
