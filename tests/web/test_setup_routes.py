"""The Setup page (#473): setup steps and rig settings on two tabs.

Seam (Aaron, 2026-11-23): GET /setup shows both tabs, the photo quality now in force and the
photo size in pixels. Misses the layout and the JavaScript."""

import pytest
from fastapi.testclient import TestClient

from npec_rig.app import app

pytestmark = pytest.mark.unit


def test_setup_page_shows_both_tabs():
    page = TestClient(app).get("/setup").text

    assert "Setup steps" in page
    assert "Rig settings" in page


def test_setup_page_shows_the_photo_quality_in_force():
    client = TestClient(app)
    client.post("/api/photo-quality", json={"quality": 95, "chroma": "4:4:4"})

    page = client.get("/setup").text

    assert "Most detail in use, 95 full" in page


def test_setup_page_shows_the_size_of_the_newest_photo(monkeypatch, tmp_path):
    from PIL import Image

    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    day = tmp_path / "rig" / "2027-01-01"
    day.mkdir(parents=True)
    Image.new("RGB", (640, 480)).save(day / "080000_000000.jpg")  # the older photo
    Image.new("RGB", (64, 48)).save(day / "090000_000000.jpg")

    page = TestClient(app).get("/setup").text

    assert "Photos are 64 x 48 px" in page


def test_setup_page_opens_when_the_newest_photo_cannot_be_read(monkeypatch, tmp_path):
    # A photo still being written, or cut short: the page must still open, since it links to the
    # pages that fix the rig (review of PR #475).
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    day = tmp_path / "rig" / "2027-01-01"
    day.mkdir(parents=True)
    (day / "090000_000000.jpg").write_bytes(b"\xff\xd8\xff\xe0 not a whole photo")

    response = TestClient(app).get("/setup")

    assert response.status_code == 200
    assert "Photo size is not known yet" in response.text


def test_setup_page_warns_while_an_unnamed_experiment_runs():
    # Names are optional (review of PR #475): the warnings follow a running experiment, not its name.
    client = TestClient(app)
    experiment = client.post("/api/experiments", json={}).json()
    client.post(f"/api/experiments/{experiment['id']}/start")

    page = client.get("/setup").text

    assert page.count("Experiment running") == 2


def test_setup_page_opens_and_links_the_setup_pages_when_the_database_cannot_be_read(monkeypatch, tmp_path):
    # rig.db locked or unreadable (review of PR #475): the page still links to the pages that
    # repair the rig.
    monkeypatch.setenv("NPEC_RIG_DB_PATH", str(tmp_path))  # a folder, not a database

    response = TestClient(app).get("/setup")

    assert response.status_code == 200
    for href in ("/setup/focus", "/setup/calibration", "/setup/validation", "/setup/health-check"):
        assert f'href="{href}"' in response.text


def test_setup_page_has_auto_exposure_with_its_warning_and_steppers():
    # Seam (Aaron, 2026-11-26, #531): Auto exposure, Exposure and Gain are set on Rig settings.
    # Misses the layout and the JavaScript.
    page = TestClient(app).get("/setup").text

    assert 'id="auto-exposure"' in page
    assert 'id="exposure-row"' in page
    assert 'id="gain-row"' in page
    assert "the rig cannot tell photos taken with the lights off. Keep it on during an experiment." in page
    assert "About Auto exposure" in page
