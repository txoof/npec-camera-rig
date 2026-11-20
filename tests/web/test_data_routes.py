"""The Data page and its time lapse videos (#64)."""
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from npec_rig import database
from npec_rig.app import app
from tests.helpers import turned_tray_photo

pytestmark = pytest.mark.unit

START = datetime(2027, 3, 1, 10, 0, tzinfo=timezone.utc)
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")


@pytest.fixture
def experiment() -> int:
    e = database.create_experiment(uuid="u-64", created_at=START.isoformat())
    database.start_experiment(e["id"], now=START.isoformat(), folder="experiments/x")
    return e["id"]


def _request(experiment_id: int) -> dict:
    return {"experiment_id": experiment_id, "tray_id": 4, "start": START.isoformat(),
            "end": (START + timedelta(hours=3)).isoformat(), "per_hour": 1, "method": "fixed"}


def _made(client: TestClient, video_id: str, timeout_s: float = 60) -> dict:
    """Wait, as the page does, until the video is made: its progress."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        progress = client.get(f"/api/data/timelapse/{video_id}").json()
        if progress["state"] in ("ready", "failed"):
            return progress
        time.sleep(0.05)
    raise AssertionError(f"video {video_id} not made in {timeout_s} s")


@needs_ffmpeg
def test_a_tray_video_is_made_in_the_background_and_downloads_as_an_mp4_of_its_frames(experiment, tmp_path):
    turned_tray_photo(experiment, START)
    turned_tray_photo(experiment, START + timedelta(hours=1))
    client = TestClient(app)

    started = client.post("/api/data/timelapse", json=_request(experiment))
    assert started.status_code == 200, started.text
    progress = _made(client, started.json()["id"])
    assert progress["state"] == "ready", progress
    assert progress["frames"] == 2

    video = client.get(f"/api/data/timelapse/{started.json()['id']}/download")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    file = tmp_path / "tray.mp4"
    file.write_bytes(video.content)
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=nb_read_frames,width,height,codec_name", "-of", "json", str(file)],
        capture_output=True, text=True, check=True).stdout)["streams"][0]
    assert probe["codec_name"] == "h264"
    assert int(probe["nb_read_frames"]) == 2
    assert probe["width"] == 610


@needs_ffmpeg
def test_a_video_is_kept_after_its_download_and_a_restart_until_the_next_one_is_started(experiment):
    from npec_rig import timelapse

    turned_tray_photo(experiment, START)
    client = TestClient(app)
    first = client.post("/api/data/timelapse", json=_request(experiment)).json()["id"]
    assert _made(client, first)["state"] == "ready"

    assert client.get(f"/api/data/timelapse/{first}/download").status_code == 200
    timelapse.clear()  # as the app does when it starts
    assert client.get(f"/api/data/timelapse/{first}").json()["state"] == "ready"
    assert client.get(f"/api/data/timelapse/{first}/download").status_code == 200

    second = client.post("/api/data/timelapse", json=_request(experiment)).json()["id"]
    assert client.get(f"/api/data/timelapse/{first}").json()["state"] == "replaced"
    assert _made(client, second)["state"] == "ready"
    assert [f.name for f in timelapse.videos_root().iterdir()] == [second]


@needs_ffmpeg
def test_the_data_page_opened_again_offers_the_latest_video(experiment):
    turned_tray_photo(experiment, START)
    client = TestClient(app)
    video = client.post("/api/data/timelapse", json=_request(experiment)).json()["id"]
    assert _made(client, video)["state"] == "ready"

    page = client.get(f"/data?experiment={experiment}")

    assert f'href="/api/data/timelapse/{video}/download"' in page.text


def test_with_no_ffmpeg_a_video_is_refused_with_the_reason(experiment, monkeypatch, tmp_path):
    turned_tray_photo(experiment, START)
    monkeypatch.setenv("PATH", str(tmp_path))  # a PATH with no ffmpeg on it

    refused = TestClient(app).post("/api/data/timelapse", json=_request(experiment))

    assert refused.status_code == 409
    assert "ffmpeg is not installed" in refused.json()["detail"]


def test_the_data_page_opens_from_the_rail_and_offers_the_experiments_trays(experiment):
    turned_tray_photo(experiment, START)
    database.update_experiment(experiment, name="Potato light")

    page = TestClient(app).get(f"/data?experiment={experiment}")

    assert page.status_code == 200
    assert '<a class="rail-btn hit" href="/data" aria-current="page">' in page.text
    assert "Potato light" in page.text
    assert 'data-value="4"' in page.text  # tray 4, the tray in its photos


@needs_ffmpeg
def test_a_video_replaced_by_a_newer_one_says_so_and_names_the_newer_one(experiment):
    turned_tray_photo(experiment, START)
    client = TestClient(app)
    first = client.post("/api/data/timelapse", json=_request(experiment)).json()["id"]
    assert _made(client, first)["state"] == "ready"
    second = client.post("/api/data/timelapse", json=_request(experiment)).json()["id"]

    replaced = client.get(f"/api/data/timelapse/{first}").json()

    assert replaced["state"] == "replaced"
    assert replaced["newer"] == second
    _made(client, second)


def test_a_request_with_its_start_after_its_end_or_an_unknown_cell_is_refused(experiment):
    client = TestClient(app)
    backwards = {**_request(experiment), "start": (START + timedelta(hours=3)).isoformat(), "end": START.isoformat()}
    no_such_cell = {**_request(experiment), "cell": "Z9"}

    assert client.post("/api/data/timelapse", json=backwards).status_code == 422
    assert client.post("/api/data/timelapse", json=no_such_cell).status_code == 422
