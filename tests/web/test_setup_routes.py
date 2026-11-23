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
    assert "Photo size is known after the first photo" in response.text
