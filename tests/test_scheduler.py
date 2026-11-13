import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, scheduler
from npec_rig.app import app
from npec_rig.camera import CameraManager, SyntheticBackend

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def short_intervals_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "MIN_INTERVAL_S", 0.0)
    # Notice a start well within the tests' 0.3 s intervals, as 1 s is within the rig's 10 s.
    monkeypatch.setattr(scheduler, "CHECK_S", 0.05)


@pytest.fixture(autouse=True)
def isolated_folders(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_EXPERIMENTS_DIR", str(tmp_path / "experiments"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


@pytest.fixture(autouse=True)
def no_scheduler_left_running():
    """Wait for each test's scheduler thread to finish. Its app stop does not wait for it
    (`stop(0)`), so one still inside a slow photo would carry on into the next test, read that
    test's database and take its photos."""
    yield
    for thread in threading.enumerate():
        if thread.name == "scheduler":
            thread.join(5.0)


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



def test_photos_missed_while_the_app_was_down_say_so() -> None:
    client = TestClient(app)  # no lifespan: no scheduler runs, as while the app is down
    _experiment, _started = _start(client, 0.3)
    time.sleep(1.0)  # photos due at 0.3, 0.6 and 0.9 s pass with nobody to take them

    with TestClient(app) as client:
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 1)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["missed_by_reason"]["app_down"] >= 2
    assert schedule["missed_by_reason"]["photo_failed"] == 0


def test_photos_missed_behind_a_slow_photo_say_so() -> None:
    CameraManager.set_instance(CameraManager(SlowBackend()))
    with TestClient(app) as client:
        _start(client, 0.3)
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 2)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["missed_by_reason"]["photo_slow"] >= 1
    assert schedule["missed_by_reason"]["app_down"] == 0


class FailingBackend(SyntheticBackend):
    """A camera whose stills fail."""

    def capture_full_res(self):
        raise RuntimeError("camera timed out")


def test_failed_photos_are_counted_as_failed() -> None:
    CameraManager.set_instance(CameraManager(FailingBackend()))
    with TestClient(app) as client:
        _start(client, 0.3)
        _wait_for(
            lambda: client.get("/api/experiments").json()[0]["schedule"]["missed_by_reason"]["photo_failed"] >= 2
        )
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["missed_by_reason"]["app_down"] == 0


def test_downtime_runs_from_the_last_photo_before_it_to_the_restart() -> None:
    with TestClient(app) as client:
        _experiment, started = _start(client, 0.3)
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 1)
    client = TestClient(app)  # the app is down: no scheduler runs
    time.sleep(1.0)  # about 3 scheduled photos pass with nobody to take them
    last_photo_at = datetime.fromisoformat(database.captures_for_experiment(started["id"])[-1]["taken_at"])

    restarted_at = datetime.now(UTC)
    with TestClient(app) as client:
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["missed_by_reason"]["app_down"] >= 1)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    (period,) = schedule["downtime"]
    assert datetime.fromisoformat(period["after"]) == last_photo_at
    until = datetime.fromisoformat(period["until"])
    assert restarted_at <= until <= restarted_at + timedelta(seconds=0.5)


def test_the_photo_taken_on_return_is_listed_as_late() -> None:
    client = TestClient(app)  # no lifespan: no scheduler runs, as while the app is down
    _experiment, started = _start(client, 0.3)
    time.sleep(1.0)

    restarted_at = datetime.now(UTC)
    with TestClient(app) as client:
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 1)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    first_photo = database.captures_for_experiment(started["id"])[0]
    (late, *_) = schedule["late_photos"]
    assert datetime.fromisoformat(late["due"]) < restarted_at
    assert late["taken"] == first_photo["taken_at"]
    elapsed = datetime.fromisoformat(late["taken"]) - datetime.fromisoformat(late["due"])
    assert late["late_s"] == pytest.approx(elapsed.total_seconds())


def test_photos_taken_on_time_are_not_listed_as_late() -> None:
    with TestClient(app) as client:
        _start(client, 0.3)
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 2)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["late_photos"] == []
    assert schedule["downtime"] == []


def _photo_at(experiment_id: int, taken_at: str) -> int:
    return database.record_capture(
        taken_at=taken_at, path=f"experiments/x/{taken_at}", purpose="capture", experiment_id=experiment_id,
        calibration=None, validation=None, lens_position=None, focus_locked_at=None, exposure_us=None,
        analogue_gain=None, flags=[],
    )


def test_each_downtime_runs_from_the_last_photo_before_its_restart_or_from_the_schedules_start() -> None:
    """A schedule from 10:00, a photo a minute. Restarts at 10:00:30 (no photo yet), 10:05:30 (after
    the 10:03 photo) and 10:05:45 (no photo since the one before). Worked out by hand (#416)."""
    experiment = database.create_experiment(uuid="u-416", created_at="2027-01-01T09:00:00+00:00", interval_s=60)
    database.start_experiment(experiment["id"], now="2027-01-01T10:00:00+00:00", folder="experiments/x")
    for minute in ("01", "02", "03", "06"):
        _photo_at(experiment["id"], f"2027-01-01T10:{minute}:00+00:00")
    for started_at in ("10:00:30", "10:05:30", "10:05:45"):
        database.record_app_start(f"2027-01-01T{started_at}+00:00")

    downtime = scheduler.schedule(database.get_experiment(experiment["id"]))["downtime"]

    assert downtime == [
        {"after": "2027-01-01T10:00:00+00:00", "until": "2027-01-01T10:00:30+00:00"},
        {"after": "2027-01-01T10:03:00+00:00", "until": "2027-01-01T10:05:30+00:00"},
        {"after": "2027-01-01T10:03:00+00:00", "until": "2027-01-01T10:05:45+00:00"},
    ]


def test_a_photo_is_late_when_the_app_came_back_after_it_was_due_and_by_the_time_it_was_taken() -> None:
    """#416 review, worked out by hand. A schedule from 10:00, a photo a minute. The 10:01 photo,
    taken at 10:01:00 by an app started at exactly 10:01:00, was not due while the app was down. The
    10:03 photo, taken at 10:04:30 by the app started at that moment, is 90 s late. The 10:05 photo,
    taken 2 s after it was due with no start in between, is on time."""
    experiment = database.create_experiment(uuid="u-416b", created_at="2027-01-01T09:00:00+00:00", interval_s=60)
    since = "2027-01-01T10:00:00+00:00"
    database.start_experiment(experiment["id"], now=since, folder="experiments/x")
    taken = {1: "10:01:00", 3: "10:04:30", 5: "10:05:02"}
    database.record_scheduled_photos(experiment["id"], since, [
        (slot, f"2027-01-01T10:0{slot}:00+00:00", _photo_at(experiment["id"], f"2027-01-01T{at}+00:00"), None)
        for slot, at in taken.items()
    ])
    for started_at in ("10:01:00", "10:04:30"):
        database.record_app_start(f"2027-01-01T{started_at}+00:00")

    late = scheduler.schedule(database.get_experiment(experiment["id"]))["late_photos"]

    assert late == [{"due": "2027-01-01T10:03:00+00:00", "taken": "2027-01-01T10:04:30+00:00", "late_s": 90.0}]
