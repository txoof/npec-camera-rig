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
from tests.helpers import lock_held, read_rig_db

pytestmark = pytest.mark.unit


# The clock these tests run the scheduler on. The rig's shortest photo interval is 10 s
# (scheduler.MIN_INTERVAL_S, patched away below); these tests run the same behaviour on a clock
# 200 times faster. A synthetic photo takes about 10 ms on the controller (measured 2026-11-26:
# six photos through captures.take_photo took 80, 18, 8, 9, 10 and 10 ms), so a slot here is
# about five photo-times wide where the rig's 10 s slot, with its 3 s photo, is about three:
# the clock is faster but no tighter than the rig's own.
#
# What scales with this number: how often a photo is due, how many slots a sleep or a lock
# spans, and any wait written as `_slots(n)`.
#
# What does not: the work that happens inside a slot. Starting the app, opening rig.db, encoding
# a JPEG, writing a file and one scheduler poll cost the same whatever this number says, and
# several times more on a Pi 5 and on the Arm64 CI runner than on the x86 box the figures below
# were measured on. A budget that has to cover that work is written against PHOTO_WORK_S or in
# whole seconds, never as a fraction of a slot: lowering INTERVAL_S shortens the slots, it does
# not speed the machine up (#547 review).
INTERVAL_S = 0.05

# One scheduled photo's fixed cost on the controller: the synthetic still, its info file, the
# tick's own database work. Measured 2026-11-26, see the figures above. It does not scale with
# INTERVAL_S, so the tests that have to fit a known number of photos into a known time are
# written against it.
PHOTO_WORK_S = 0.025

# How long a photo's row waits for rig.db in the tests that lock it. It stands for the rig's
# 10 s wait being far shorter than the lock, and nothing else, so it is absolute: a photo pays
# it twice (captures.take_photo, once before the file is saved and once after) and the scheduler
# pays it again on each catch-up attempt, out of a budget that does not shrink with INTERVAL_S.
SHORT_DB_WAIT_S = 0.005


def _slots(n: float) -> float:
    """`n` photo intervals, in seconds."""
    return n * INTERVAL_S


def _locked_photos_s(n: float) -> float:
    """How long `n` scheduled photos take while rig.db is locked. A photo cannot come faster
    than its slot, and it cannot come faster than its own work plus the lock waits it pays, so
    the slower of the two sets the pace."""
    return n * max(INTERVAL_S, PHOTO_WORK_S + 2 * SHORT_DB_WAIT_S)


@pytest.fixture(autouse=True)
def short_intervals_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler, "MIN_INTERVAL_S", 0.0)
    # Notice a start a sixth of an interval after it, as the rig's 1 s is within its 10 s.
    monkeypatch.setattr(scheduler, "CHECK_S", _slots(1 / 6))


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


def _wait_for(condition, timeout_s: float = 10.0, poll_s: float = 0.02) -> None:
    """Poll until `condition` holds. The timeout is generous on purpose: it costs nothing when
    the condition comes quickly, and a test that waits for the thing it is about cannot be made
    flaky by a slow machine the way a fixed sleep can.

    `condition` usually reads rig.db, and several of these tests shorten settings.LOCK_WAIT_S,
    which is the wait the test's own reads get as well: a read landing on the scheduler writing
    a row would then raise "database is locked" rather than answer. That is the rig working, not
    failing, so the read is tried again and the deadline above still decides when the test
    fails (`read_rig_db`, #561)."""
    deadline = time.monotonic() + timeout_s
    while not read_rig_db(condition):
        assert time.monotonic() < deadline, "timed out"
        time.sleep(poll_s)


def _wait_for_the_short_db_wait_to_take(experiment_id: int) -> None:
    """Wait for one more photo, after settings.LOCK_WAIT_S has been shortened and before rig.db
    is locked.

    sqlite3 fixes a connection's busy timeout when the connection is opened, and database._connect
    reads settings.LOCK_WAIT_S at that moment. A connection the scheduler opened just before the
    test shortened it still waits the full 10 s, so a lock taken between that connection being
    opened and its insert leaves the scheduler inside one tick for the whole lock: no photo is
    taken, nothing is logged, and the test reads zero. Seen pinned to one core against one busy
    competitor, about 6 failures in 45 runs, and never on an idle machine; the shorter the wait,
    the more catch-up attempts the scheduler makes per slot and the wider the window (#547
    review).

    One photo taken after the change means the scheduler has finished that tick, so every
    connection it has open when the lock arrives was opened with the short wait."""
    taken = _photos(experiment_id)
    _wait_for(lambda: _photos(experiment_id) > taken)


def _wait_for_a_missed_slot(since: str, interval_s: float) -> None:
    """Block until one photo slot has come due with nobody to take it, and the next slot is
    between a fifth and a third of the way through.

    A restart has to land at a known place inside a slot. scheduler._tick takes the photo of
    whichever slot is current when it runs, so a restart that straddles a slot boundary gets the
    photo of the slot after the one the test measured itself against: that photo was due after
    the restart, not before it, and it is not listed as late at all. On the Arm64 CI runner that
    is what happened, at the old 0.3 s interval, the due time 0.2 s after the restart (#559).

    Polled rather than slept. A sleep of so many intervals assumes the work before it took no
    time, and a sleep on a loaded machine overshoots; either leaves the restart anywhere in the
    slot, including past its end. This returns at a phase the caller can rely on, however long
    anything before it took."""
    start = datetime.fromisoformat(since)
    while True:
        elapsed = (datetime.now(UTC) - start).total_seconds()
        if elapsed >= interval_s and interval_s / 5 <= elapsed % interval_s < interval_s / 3:
            return
        time.sleep(0.001)


def test_a_running_schedule_takes_photos_into_the_experiment() -> None:
    with TestClient(app) as client:
        experiment, _started = _start(client, INTERVAL_S)
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 2)


class HeldBackend(SyntheticBackend):
    """A camera whose stills wait, one at a time, for the test to let them through.

    It exists so a test about the moment a stop lands mid-photo can reach that moment every run
    instead of racing the scheduler for it (#570).

    Counting semaphores, not events: a still that begins while the test is between calls still
    registers on `_begun`, and one `let_the_still_finish()` lets exactly one still through. With
    events, a release left set lets an unknown number of stills run free, which is how the first
    version of this fix was itself flaky."""

    def __init__(self) -> None:
        super().__init__()
        self._begun = threading.Semaphore(0)  # one per still that has begun and is waiting
        self._allowed = threading.Semaphore(0)  # one per still the test has let through

    def capture_full_res(self):
        self._begun.release()
        assert self._allowed.acquire(timeout=10.0), "the test never let the still finish"
        return super().capture_full_res()

    def wait_for_a_still_to_begin(self) -> None:
        """Block until the scheduler is inside a still, held there until it is let through."""
        assert self._begun.acquire(timeout=10.0), "the scheduler began no photo"

    def let_the_still_finish(self) -> None:
        self._allowed.release()

    def no_still_begins_within(self, seconds: float) -> bool:
        """True when the scheduler starts no still at all in `seconds`."""
        if self._begun.acquire(timeout=seconds):
            self._begun.release()
            return False
        return True


def test_stopping_the_experiment_stops_the_photos() -> None:
    """The stop ends the schedule: no further photo is even begun. The photo already being taken
    when it lands is kept out of the experiment and its slot is recorded as missed.

    What the rig promises is that no *new* photo starts after the stop. It cannot promise that no
    photo is saved after it: `scheduler._tick` reads the running experiment, then takes the photo,
    so a still already underway when the stop reaches rig.db finishes afterwards and its
    `taken_at` is later than `ended_at`. `_tick` handles that on purpose, recording the slot with
    the reason asserted below and leaving the photo out of the experiment as a rig photo.

    Until #570 this test asserted that no photo at all followed the stop, which is the one thing
    the rig does not promise. It passed only when the stop happened to reach rig.db inside the gap
    between two stills, and on a loaded controller it failed about half the time. `HeldBackend`
    removes the luck: the stop always lands mid-photo, so the case the rig was built for is the
    case the test measures."""
    camera = HeldBackend()
    CameraManager.set_instance(CameraManager(camera))
    with TestClient(app) as client:
        experiment, started = _start(client, INTERVAL_S)
        since = started["schedule"]["since"]

        camera.wait_for_a_still_to_begin()
        camera.let_the_still_finish()
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 1)

        # The next still is held open, so the stop lands in the middle of it every run. No other
        # still can finish meanwhile: each one needs a release of its own.
        camera.wait_for_a_still_to_begin()
        photos_in_the_experiment = len(database.captures_for_experiment(experiment["id"]))
        client.post(f"/api/experiments/{experiment['id']}/stop")
        camera.let_the_still_finish()

        # Its slot is recorded as missed, with the photo left out of the experiment.
        _wait_for(
            lambda: database.schedule_progress(experiment["id"], since)["missed_reasons"].get(
                "experiment stopped during the photo"
            )
            == 1
        )
        assert len(database.captures_for_experiment(experiment["id"])) == photos_in_the_experiment

        # The schedule has stopped: over the next three or four slots no still is begun at all.
        assert camera.no_still_begins_within(_slots(3.4)), "a photo was started after the stop"
        assert client.get("/api/experiments").json()[0]["schedule"] is None


def test_after_a_restart_the_schedule_resumes_and_counts_the_photos_missed_while_down() -> None:
    # Started while the app is down: no lifespan, so no scheduler runs.
    client = TestClient(app)
    experiment, _started = _start(client, INTERVAL_S)
    time.sleep(_slots(3.4))  # slots 1, 2 and 3 pass with nobody to take them

    with TestClient(app) as client:
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 1)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["photos_taken"] >= 1
    assert schedule["photos_missed"] >= 2


class SlowBackend(SyntheticBackend):
    """A camera whose still takes longer than the schedule's interval."""

    def capture_full_res(self):
        time.sleep(_slots(2.4))
        return super().capture_full_res()


def test_a_photo_slower_than_the_interval_skips_the_next_and_counts_it_missed() -> None:
    CameraManager.set_instance(CameraManager(SlowBackend()))
    with TestClient(app) as client:
        experiment, _started = _start(client, INTERVAL_S)
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 2)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    # Each photo takes 2.4 slots, so it spans at least one more, which is skipped, not queued.
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
    _experiment, _started = _start(client, INTERVAL_S)
    time.sleep(_slots(3.4))  # photos due at slots 1, 2 and 3 pass with nobody to take them

    with TestClient(app) as client:
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 1)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["missed_by_reason"]["app_down"] >= 2
    assert schedule["missed_by_reason"]["photo_failed"] == 0


def test_photos_missed_behind_a_slow_photo_say_so() -> None:
    CameraManager.set_instance(CameraManager(SlowBackend()))
    with TestClient(app) as client:
        _start(client, INTERVAL_S)
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
        _start(client, INTERVAL_S)
        _wait_for(
            lambda: client.get("/api/experiments").json()[0]["schedule"]["missed_by_reason"]["photo_failed"] >= 2
        )
        schedule = client.get("/api/experiments").json()[0]["schedule"]
    assert schedule["missed_by_reason"]["app_down"] == 0


def test_downtime_runs_from_the_last_photo_before_it_to_the_restart() -> None:
    with TestClient(app) as client:
        _experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: client.get("/api/experiments").json()[0]["schedule"]["photos_taken"] >= 1)
    client = TestClient(app)  # the app is down: no scheduler runs
    time.sleep(_slots(3.4))  # about 3 scheduled photos pass with nobody to take them
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
    # Six times the usual slot, and the restart placed a fifth to a third of the way into one
    # (_wait_for_a_missed_slot). What has to fit in the rest of that slot -- TestClient's
    # lifespan, the scheduler thread starting, one CHECK_S poll -- is fixed work that does not
    # shrink with INTERVAL_S, so the slot is made long enough to hold it many times over: at
    # least 200 ms of slot left, against 25 to 34 ms measured from the restart to the photo,
    # pinned to one core with two busy competitors (#547 review, #559).
    interval_s = _slots(6)
    client = TestClient(app)  # no lifespan: no scheduler runs, as while the app is down
    _experiment, started = _start(client, interval_s)
    _wait_for_a_missed_slot(started["schedule"]["since"], interval_s)

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
        _start(client, INTERVAL_S)
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
        experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: len(database.captures_for_experiment(experiment["id"])) >= 1)
        monkeypatch.setattr(settings, "LOCK_WAIT_S", SHORT_DB_WAIT_S)
        _wait_for_the_short_db_wait_to_take(experiment["id"])
        folder = captures.experiments_root() / started["folder"]
        before = len(list(folder.rglob("*.jpg")))
        with lock_held(_slots(3.4)):  # three or four slots come due while nothing can be written
            pass
        # The test is about a photo saved under the lock, so there has to be one. Without this
        # the wait below could pass on its first poll having tested nothing (#547 review).
        assert len(list(folder.rglob("*.jpg"))) > before
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        since = started["periods"][-1]["started_at"]

        def settled() -> bool:
            on_disk = {p.stem for p in folder.rglob("*.jpg")}
            recorded = {Path(c["path"]).name for c in database.captures_for_experiment(experiment["id"])}
            progress = database.schedule_progress(experiment["id"], since)
            return on_disk <= recorded and progress["last_slot"] == progress["photos_taken"] + progress["photos_missed"]

        # No settling pause before the wait: the photos saved under the lock are on disk without
        # rows the moment it ends, so `settled` is false until the scheduler has done the work.
        _wait_for(settled)
        client.post(f"/api/experiments/{experiment['id']}/stop")


def _photos(experiment_id: int) -> int:
    """How many photos rig.db holds for the experiment. Retried while rig.db is locked: the
    tests that shorten settings.LOCK_WAIT_S shorten this read's wait too (`read_rig_db`, #561)."""
    return read_rig_db(lambda: len(database.captures_for_experiment(experiment_id)))


# How long after its slot was due the photo below was taken. It has to land inside the slot:
# database.link_unlinked_slots matches a photo to a slot only within one interval of it, and
# captures.adopt_unrecorded_photos reads the time back out of the file name, so this is written
# into the name as whole microseconds and must stay under one slot. It is also written with
# `%06d` and read back as the fractional part of a timestamp, so it has to stay under a whole
# second however long a slot is: a third of a slot, capped (#547 review).
_LATE_BY_US = min(int(_slots(1 / 3) * 1_000_000), 999_999)


def _old_photo_without_a_row(started: dict, experiment_id: int, sidecar_text) -> str:
    """A photo saved on 25 October whose row could not be written, as the scheduler before #464
    left it: its slot neither taken nor missed (#481). Its info file is `sidecar_text(record)`.
    Returns its path as rig.db stores it."""
    stills = captures.experiments_root() / started["folder"] / "stills"
    first = next(stills.rglob("*.jpg"))
    day = stills / "2026-10-25"
    day.mkdir()
    name = f"120000_{_LATE_BY_US:06d}"
    shutil.copy(first, day / f"{name}.jpg")
    record = json.loads(first.with_suffix(".json").read_text())
    record["timestamp"] = f"2026-10-25T12:00:00.{_LATE_BY_US:06d}+00:00"
    (day / f"{name}.json").write_text(sidecar_text(record))
    database.record_scheduled_photos(
        experiment_id, "2026-10-25T00:00:00+00:00", [(720, "2026-10-25T12:00:00+00:00", None, None)]
    )
    return f"experiments/{started['folder']}/stills/2026-10-25/{name}"


def _before_clock_and_photo_quality(record: dict) -> str:
    """An info file as photos had it before 2 November (#344, "clock") and 5 November (#359,
    "photo_quality")."""
    del record["clock"], record["photo_quality"]
    return json.dumps(record)


def test_an_old_photo_without_a_row_gets_its_row_and_the_scheduled_photos_go_on() -> None:
    """#481: on main after #464, adding this photo's row raised KeyError on every tick, before the
    tick's photo, so no scheduled photo was ever taken again."""
    with TestClient(app) as client:
        experiment, started = _start(client, INTERVAL_S)
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
        experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        path = _old_photo_without_a_row(started, experiment["id"], lambda record: "")
        before = _photos(experiment["id"])
        _wait_for(lambda: _photos(experiment["id"]) >= before + 3, timeout_s=5)
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]), timeout_s=5)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert path not in database.captures_by_path([path])
    reasons = database.schedule_progress(experiment["id"], "2026-10-25T00:00:00+00:00")["missed_reasons"]
    assert reasons == {"the photo was saved but its record could not be read": 1}


OLD_SINCE = "2026-10-25T00:00:00+00:00"


def _scheduled_photo_without_a_row(started: dict, experiment_id: int, *, due_at: str, taken_at: str) -> str:
    """A scheduled photo saved while rig.db was locked, as the scheduler since #488 leaves it:
    its info file records its slot (720 of the schedule from OLD_SINCE), its row is not there and
    its slot is neither taken nor missed. It is due at `due_at` and saved at `taken_at`, in the
    folder of that UTC day. Returns its path as rig.db stores it."""
    taken = datetime.fromisoformat(taken_at)
    stills = captures.experiments_root() / started["folder"] / "stills"
    first = next(stills.rglob("*.jpg"))
    day = stills / f"{taken:%Y-%m-%d}"
    day.mkdir(exist_ok=True)
    name = f"{taken:%H%M%S_%f}"
    shutil.copy(first, day / f"{name}.jpg")
    record = json.loads(first.with_suffix(".json").read_text())
    record["timestamp"] = taken_at
    record["schedule"] = {"since": OLD_SINCE, "slot": 720, "due_at": due_at}
    (day / f"{name}.json").write_text(json.dumps(record))
    database.record_scheduled_photos(experiment_id, OLD_SINCE, [(720, due_at, None, None)])
    return f"experiments/{started['folder']}/stills/{taken:%Y-%m-%d}/{name}"


def test_a_manual_photo_in_the_same_interval_is_not_linked_to_the_slot() -> None:
    """#488: a slot was linked to the earliest Capture photo within its interval, which could be
    one taken by hand. The scheduled photo's info file names its slot, so that is the one."""
    with TestClient(app) as client:
        experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        database.record_capture(
            taken_at="2026-10-25T12:00:00.000001+00:00", path="experiments/x/stills/2026-10-25/120000_000001",
            purpose="capture", experiment_id=experiment["id"], calibration=None, validation=None,
            lens_position=None, focus_locked_at=None, exposure_us=None, analogue_gain=None, flags=[],
        )
        path = _scheduled_photo_without_a_row(
            started, experiment["id"], due_at="2026-10-25T12:00:00+00:00",
            taken_at=f"2026-10-25T12:00:00.{_LATE_BY_US:06d}+00:00",
        )
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]), timeout_s=5)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert database.scheduled_photos_taken(experiment["id"], OLD_SINCE) == [
        {"due_at": "2026-10-25T12:00:00+00:00", "taken_at": f"2026-10-25T12:00:00.{_LATE_BY_US:06d}+00:00"}
    ]
    assert path in database.captures_by_path([path])


def test_a_slow_photo_saved_after_its_interval_and_after_midnight_is_still_linked_to_its_slot() -> None:
    """#488: a photo saved more than one interval after its slot was due was marked "not found",
    and one saved on the next UTC day was never looked for. Due at 23:59:59 on 25 October, saved
    at 00:00:30 on the 26th, with a 0.05 s interval here."""
    with TestClient(app) as client:
        experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        path = _scheduled_photo_without_a_row(
            started, experiment["id"], due_at="2026-10-25T23:59:59+00:00", taken_at="2026-10-26T00:00:30+00:00",
        )
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]), timeout_s=5)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert database.schedule_progress(experiment["id"], OLD_SINCE)["missed_reasons"] == {}
    assert database.scheduled_photos_taken(experiment["id"], OLD_SINCE) == [
        {"due_at": "2026-10-25T23:59:59+00:00", "taken_at": "2026-10-26T00:00:30+00:00"}
    ]
    assert path in database.captures_by_path([path])


# The photos the lock in the next test has to hold, and how much longer than their measured cost
# it is held. The 7 is the behaviour under test: on main after #464 it was 0. The margin is over
# measured work that does not shrink with INTERVAL_S, so the lock is a multiple of
# `_locked_photos_s`, not of the slot (#547 review).
_PHOTOS_UNDER_THE_LOCK = 7
_LOCK_MARGIN = 4


def test_photos_are_still_taken_while_rig_db_stays_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    """#481, decision 1 (Aaron, 2026-11-23): the photo is taken first, the database work after it.
    On main after #464 no photo was taken from the first locked write until the lock ended. Each
    photo's row waits SHORT_DB_WAIT_S for rig.db and fails, so a photo and its failed row fit
    inside one slot, and the photos come one a slot. The lock gives each of the 7 photos four
    slots, 200 ms, where one measures 50 ms pinned to a single core with busy competitors: a
    machine four times slower still takes them."""
    with TestClient(app) as client:
        experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        folder = captures.experiments_root() / started["folder"]
        monkeypatch.setattr(settings, "LOCK_WAIT_S", SHORT_DB_WAIT_S)
        _wait_for_the_short_db_wait_to_take(experiment["id"])
        before = len(list(folder.rglob("*.jpg")))
        with lock_held(_LOCK_MARGIN * _locked_photos_s(_PHOTOS_UNDER_THE_LOCK)):
            pass
        during = len(list(folder.rglob("*.jpg"))) - before
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert during >= _PHOTOS_UNDER_THE_LOCK


def test_slots_lost_while_rig_db_is_locked_are_counted_as_rig_db_could_not_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#481, decision 4 (Aaron, 2026-11-23): a slot lost because rig.db could not be written has
    its own reason, not "the previous photo took longer than the interval". Each photo's row
    waits 1.7 slots for the lock, longer than one slot, so the lock costs slots."""
    with TestClient(app) as client:
        experiment, _started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        monkeypatch.setattr(settings, "LOCK_WAIT_S", _slots(5 / 3))
        _wait_for_the_short_db_wait_to_take(experiment["id"])
        with lock_held(_slots(10)):
            pass
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        _wait_for(lambda: not database.unlinked_slots(experiment["id"]) and _photos(experiment["id"]) >= 4)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert schedule["missed_by_reason"]["db_locked"] >= 2


def test_slots_lost_to_a_lock_shorter_than_the_wait_are_counted_as_rig_db_could_not_be_written() -> None:
    """#481 review: the usual lock is shorter than the 10 s wait, so the photo's row waits and
    is then written. The slots that pass while it waits were lost to the database, not to a slow
    photo. A five-slot lock, well inside the 10 s wait, holds the row of the photo taken under it."""
    with TestClient(app) as client:
        experiment, _started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        with lock_held(_slots(5)):
            pass
        count = _photos(experiment["id"])
        _wait_for(lambda: _photos(experiment["id"]) >= count + 2)
        schedule = client.get("/api/experiments").json()[0]["schedule"]
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert schedule["missed_by_reason"]["db_locked"] >= 2


def test_a_photo_taken_during_a_lock_gets_its_row_before_the_next_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    """#481 review: the database work waits for a later photo only when there is no time before
    it. With eight of the usual slots between photos, the first photo's row fails while rig.db is
    locked; once the lock ends, its row and slot are written well before the second photo is due.

    The lock starts just after the experiment does and runs to half way between the first photo
    and the second, so the first photo is taken and its row refused under the lock, and the lock
    is over half an interval before the second photo is due. A photo does some of its database
    work before the file is saved (captures.take_photo), so each of those waits has to fit in
    that half interval too: the wait for the lock is SHORT_DB_WAIT_S."""
    interval_s = _slots(8)
    monkeypatch.setattr(settings, "LOCK_WAIT_S", SHORT_DB_WAIT_S)
    with TestClient(app) as client:
        experiment, started = _start(client, interval_s)
        folder = captures.experiments_root() / started["folder"]
        # Done once on a new rig.db, before the lock: the camera's settings table, the JPEG setting.
        CameraManager.instance()
        settings.photo_quality_in_use()
        with lock_held(1.5 * interval_s):  # the first photo, due one interval in, is taken under it
            pass
        assert len(list(folder.rglob("*.jpg"))) == 1
        # The timeout stays generous, as _wait_for's does: "before the second photo is due" is
        # checked by the counts read straight after it, not by racing a deadline against work
        # that does not shrink with INTERVAL_S (#547 review).
        _wait_for(lambda: _photos(experiment["id"]) >= 1 and not database.unlinked_slots(experiment["id"]))
        on_disk = len(list(folder.rglob("*.jpg")))
        recorded = _photos(experiment["id"])
        # Both counts are read and the lock is long over, so the short wait has no job left.
        # Restored before the stop, as the other locked tests do: the stop writes rig.db, and
        # TestClient re-raises what the route raised, so a stop that landed on the scheduler
        # writing a row would fail the test for the wait, not for the behaviour (#561).
        monkeypatch.setattr(settings, "LOCK_WAIT_S", 10.0)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    assert (on_disk, recorded) == (1, 1)


def _info_file(path: str) -> dict:
    """The info file of the photo at `path`, as rig.db stores it."""
    return json.loads((captures.experiments_root().parent / path).with_suffix(".json").read_text())


def test_a_scheduled_photos_info_file_records_its_slot() -> None:
    """#488: the slot is written into the photo's own info file, so a row added later is linked to
    its slot by name, not by guessing from the time."""
    with TestClient(app) as client:
        experiment, started = _start(client, INTERVAL_S)
        _wait_for(lambda: _photos(experiment["id"]) >= 1)
        client.post(f"/api/experiments/{experiment['id']}/stop")
    since = started["periods"][-1]["started_at"]
    first = database.captures_for_experiment(experiment["id"])[0]
    schedule = _info_file(first["path"])["schedule"]
    assert schedule["since"] == since
    assert schedule["slot"] >= 1
    assert datetime.fromisoformat(schedule["due_at"]) > datetime.fromisoformat(since)
