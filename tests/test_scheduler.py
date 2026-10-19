import time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, scheduler
from npec_rig.app import app
from npec_rig.camera import CameraManager, SyntheticBackend

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def short_intervals_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "MIN_INTERVAL_S", 0.0)


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _start(client: TestClient, interval_s: float) -> tuple[dict, dict]:
    """Set up an experiment with a photo interval and start it."""
    experiment = client.post("/api/experiments", json={"interval_s": interval_s}).json()
    return experiment, client.post(f"/api/experiments/{experiment['id']}/start").json()


@pytest.mark.parametrize("interval_s", [60, 3600, 86400])
def test_the_next_photo_is_one_interval_after_the_start(interval_s: int) -> None:
    client = TestClient(app)
    experiment, started = _start(client, interval_s)

    schedule = started["schedule"]
    started_at = datetime.fromisoformat(started["periods"][-1]["started_at"])
    assert schedule["interval_s"] == interval_s
    assert datetime.fromisoformat(schedule["next_photo_at"]) == started_at + timedelta(
        seconds=interval_s
    )
    listed = {e["id"]: e for e in client.get("/api/experiments").json()}
    assert listed[experiment["id"]]["schedule"] == schedule


def _wait_for(condition, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_a_running_schedule_takes_photos_into_the_experiment() -> None:
    with TestClient(app) as client:
        experiment, _started = _start(client, 0.3)
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 2)


def test_stopping_the_experiment_stops_the_photos() -> None:
    with TestClient(app) as client:
        experiment, _started = _start(client, 0.3)
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 1)
        stopped = client.post(f"/api/experiments/{experiment['id']}/stop").json()
        time.sleep(1.0)
        # A photo after the stop would be a rig photo, so every photo is looked at.
        photos_after_stop = [
            c for c in captures.list_recent_captures()
            if c["record"]["taken_at"] > stopped["periods"][-1]["ended_at"]
        ]
        assert photos_after_stop == []
        assert client.get("/api/experiments").json()[0]["schedule"] is None


def test_after_a_restart_the_schedule_resumes_and_counts_the_photos_missed_while_down() -> None:
    # Started while the app is down: no lifespan, so no scheduler runs.
    client = TestClient(app)
    experiment, _started = _start(client, 0.3)
    time.sleep(1.0)  # slots at 0.3, 0.6 and 0.9 s pass with nobody to take them

    with TestClient(app) as client:
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 1)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["photos_taken"] >= 1
    assert schedule["photos_missed"] >= 2


class SlowBackend(SyntheticBackend):
    """A camera whose still takes longer than the schedule's interval."""

    def capture_full_res(self):
        time.sleep(0.7)
        return super().capture_full_res()


def test_a_photo_slower_than_the_interval_skips_the_next_and_counts_it_missed() -> None:
    CameraManager.set_instance(CameraManager(SlowBackend()))
    with TestClient(app) as client:
        experiment, _started = _start(client, 0.3)
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 2)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    # Each 0.7 s photo spans at least one more 0.3 s slot, which is skipped, not queued.
    assert schedule["photos_missed"] >= schedule["photos_taken"] - 1


def test_a_new_interval_while_running_counts_from_the_change() -> None:
    client = TestClient(app)
    experiment, started = _start(client, 3600)
    edited = client.patch(f"/api/experiments/{experiment['id']}", json={"interval_s": 7200}).json()

    schedule = edited["schedule"]
    since = datetime.fromisoformat(schedule["since"])
    assert since >= datetime.fromisoformat(started["periods"][-1]["started_at"])
    assert schedule["interval_s"] == 7200
    assert datetime.fromisoformat(schedule["next_photo_at"]) == since + timedelta(seconds=7200)
