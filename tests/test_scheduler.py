import json
import shutil
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from npec_rig import captures, database, scheduler, settings
from npec_rig.app import app
from npec_rig.camera import CameraManager, SyntheticBackend
from tests.helpers import lock_held

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


def test_a_photo_saved_while_rig_db_was_locked_gets_its_row_and_its_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    """#439: on production 11 photos were saved to disk while another writer held rig.db longer
    than a connection waits, and never got a row; their slots said neither taken nor missed."""
    with TestClient(app) as client:
        experiment, started = _start(client, 0.3)
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 1)
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.1)
        with lock_held(1.0):  # three or four slots come due while nothing can be written
            pass
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        since = started["periods"][-1]["started_at"]
        folder = captures.experiments_root() / started["folder"]

        def settled() -> bool:
            on_disk = {p.stem for p in folder.rglob("*.jpg")}
            recorded = {Path(c["path"]).name for c in database.captures_for_experiment(experiment["id"])}
            progress = database.schedule_progress(experiment["id"], since)
            return on_disk <= recorded and progress["last_slot"] == progress["photos_taken"] + progress["photos_missed"]

        time.sleep(0.5)
        _wait_for(settled)
        client.post(f"/api/experiments/{experiment['id']}/stop")


def _photos(experiment_id: int) -> int:
    return len(database.captures_for_experiment(experiment_id))


def _old_photo_without_a_row(started: dict, experiment_id: int, sidecar_text) -> str:
    """A photo saved on 25 October whose row could not be written, as the scheduler before #464
    left it: its slot neither taken nor missed (#481). Its info file is `sidecar_text(record)`.
    Returns its path as rig.db stores it."""
    stills = captures.experiments_root() / started["folder"] / "stills"
    first = next(stills.rglob("*.jpg"))
    day = stills / "2026-10-25"
    day.mkdir()
    shutil.copy(first, day / "120000_100000.jpg")
    record = json.loads(first.with_suffix(".json").read_text())
    record["timestamp"] = "2026-10-25T12:00:00.100000+00:00"
    (day / "120000_100000.json").write_text(sidecar_text(record))
    database.record_scheduled_photos(
        experiment_id, "2026-10-25T00:00:00+00:00", [(720, "2026-10-25T12:00:00+00:00", None, None)]
    )
    return f"experiments/{started['folder']}/stills/2026-10-25/120000_100000"


def _before_clock_and_photo_quality(record: dict) -> str:
    """An info file as photos had it before 2 November (#344, "clock") and 5 November (#359,
    "photo_quality")."""
    del record["clock"], record["photo_quality"]
    return json.dumps(record)


def test_an_old_photo_without_a_row_gets_its_row_and_the_scheduled_photos_go_on() -> None:
    """#481: on main after #464, adding this photo's row raised KeyError on every tick, before the
    tick's photo, so no scheduled photo was ever taken again."""
    with TestClient(app) as client:
        experiment, started = _start(client, 0.3)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        path = _old_photo_without_a_row(started, experiment["id"], _before_clock_and_photo_quality)
        before = _photos(experiment["id"])
        _wait_for(lambda: _photos(experiment["id"]) >= before + 3, timeout_s=5)
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]), timeout_s=5)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert path in database.captures_by_path([path])


def test_a_damaged_info_file_leaves_its_photo_without_a_row_and_says_so_and_the_photos_go_on() -> None:
    """#481, decision 3 (Aaron, 2026-11-23): an info file that cannot be read, as after a power
    cut (zero length), leaves the photo on disk without a row, and its slot missed with its own
    reason. On main after #464 it raised on every tick and stopped the scheduled photos."""
    with TestClient(app) as client:
        experiment, started = _start(client, 0.3)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        path = _old_photo_without_a_row(started, experiment["id"], lambda record: "")
        before = _photos(experiment["id"])
        _wait_for(lambda: _photos(experiment["id"]) >= before + 3, timeout_s=5)
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]), timeout_s=5)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert path not in database.captures_by_path([path])
    reasons = database.schedule_progress(experiment["id"], "2026-10-25T00:00:00+00:00")["missed_reasons"]
    assert reasons == {"the photo was saved but its record could not be read": 1}


def test_photos_are_still_taken_while_rig_db_stays_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """#481, decision 1 (Aaron, 2026-11-23): the photo is taken first, the database work after it.
    On main after #464 no photo was taken from the first locked write until the lock ended. A 3 s
    lock at 0.3 s intervals spans about 10 slots; each photo's row waits 0.1 s and fails."""
    with TestClient(app) as client:
        experiment, started = _start(client, 0.3)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        folder = captures.experiments_root() / started["folder"]
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.1)
        before = len(list(folder.rglob("*.jpg")))
        with lock_held(3.0):
            pass
        during = len(list(folder.rglob("*.jpg"))) - before
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert during >= 7


def test_slots_lost_while_rig_db_is_locked_are_counted_as_rig_db_could_not_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#481, decision 4 (Aaron, 2026-11-23): a slot lost because rig.db could not be written has
    its own reason, not "the previous photo took longer than the interval". Each photo's row
    waits 0.5 s for the lock, longer than the 0.3 s interval, so the lock costs slots."""
    with TestClient(app) as client:
        experiment, _started = _start(client, 0.3)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.5)
        with lock_held(3.0):
            pass
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]) and _photos(experiment["id"]) >= 4)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert schedule["missed_by_reason"]["db_locked"] >= 2


def test_slots_lost_to_a_lock_shorter_than_the_wait_are_counted_as_rig_db_could_not_be_written() -> None:
    """#481 review: the usual lock is shorter than the 10 s wait, so the photo's row waits and
    is then written. The slots that pass while it waits were lost to the database, not to a slow
    photo. A 1.5 s lock at 0.3 s intervals holds the row of the photo taken during it."""
    with TestClient(app) as client:
        experiment, _started = _start(client, 0.3)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        with lock_held(1.5):
            pass
        count = _photos(experiment["id"])
        _wait_for(lambda: _photos(experiment["id"]) >= count + 2)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert schedule["missed_by_reason"]["db_locked"] >= 2


def test_a_photo_taken_during_a_lock_gets_its_row_before_the_next_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    """#481 review: the database work waits for a later photo only when there is no time before
    it. With 2 s between photos, the first photo's row fails while rig.db is locked; once the
    lock ends, its row and slot are written well before the second photo is due."""
    monkeypatch.setattr(settings, "LOCK_WAIT_S", 0.1)
    with TestClient(app) as client:
        experiment, started = _start(client, 2.0)
        folder = captures.experiments_root() / started["folder"]
        # Done once on a new rig.db, before the lock: the camera's settings table, the JPEG setting.
        CameraManager.instance()
        settings.photo_quality_in_use()
        with lock_held(2.4):  # the first photo, due 2 s after the start, is taken under it
            pass
        assert len(list(folder.rglob("*.jpg"))) == 1
        _wait_for(lambda: _photos(experiment["id"]) == 1 and not database.unlinked_slots(experiment["id"]), timeout_s=1.2)
        on_disk = len(list(folder.rglob("*.jpg")))
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert on_disk == 1
