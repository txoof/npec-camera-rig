"""Scheduled capture: a photo every interval while an experiment runs (M3, issue #60).

Photo times are counted from the schedule's start in UTC (the latest start, resume or interval
change, `experiment.schedule_since`), not from the last photo, so the next one is known after a
restart and for any interval (a minute, an hour, a day). Slot n is due n intervals after it. Every slot is recorded in `rig.db` as taken or missed, so a
restart resumes after the last recorded slot and counts the slots that passed while it was down.
"""

import logging
import math
import threading
from datetime import UTC, datetime, timedelta

from npec_rig import captures, database, images

logger = logging.getLogger(__name__)

# The shortest interval accepted: a full-resolution still takes about 3 s (issue #43). The page
# offers 1 to 6 minutes.
MIN_INTERVAL_S = 10.0

# The longest the loop sleeps before looking at the running experiment again, so a start or stop
# is noticed within this time whatever the interval.
CHECK_S = 1.0
MISSED_APP_DOWN = "the app was not running"
MISSED_PHOTO_SLOW = "the previous photo took longer than the interval"


def _running_schedule(experiment: dict | None) -> dict | None:
    """{"since", "interval_s"} of a running experiment with an interval, else None."""
    if experiment is None or experiment["state"] != "running" or not experiment["interval_s"]:
        return None
    return {"since": experiment["schedule_since"], "interval_s": experiment["interval_s"]}


def _due_at(sched: dict, slot: int) -> datetime:
    return datetime.fromisoformat(sched["since"]) + timedelta(seconds=slot * sched["interval_s"])


def _current_slot(sched: dict, now: datetime) -> int:
    elapsed_s = (now - datetime.fromisoformat(sched["since"])).total_seconds()
    return math.floor(elapsed_s / sched["interval_s"])


def _missed_by_reason(reasons: dict[str, int]) -> dict[str, int]:
    """Missed photos counted as app down, photo slow, or photo failed (any other reason: the
    error the camera gave)."""
    app_down = reasons.get(MISSED_APP_DOWN, 0)
    photo_slow = reasons.get(MISSED_PHOTO_SLOW, 0)
    return {
        "app_down": app_down,
        "photo_slow": photo_slow,
        "photo_failed": sum(reasons.values()) - app_down - photo_slow,
    }


def _downtime(experiment_id: int, since: str, app_starts: list[str]) -> list[dict]:
    """Each time the app was down during the schedule: from the last photo taken before it came
    back (or the schedule's start) until it came back. When it went down is not known."""
    periods = []
    for started_at in app_starts:
        before = database.captures_for_experiment(experiment_id, until=started_at)
        after = max([since, *(c["taken_at"] for c in before)])
        periods.append({"after": after, "until": started_at})
    return periods


def _late_photos(experiment_id: int, since: str, app_starts: list[str]) -> list[dict]:
    """Photos due while the app was down and taken when it came back, with how late."""
    late = []
    for photo in database.scheduled_photos_taken(experiment_id, since):
        if any(photo["due_at"] < started_at <= photo["taken_at"] for started_at in app_starts):
            late_s = datetime.fromisoformat(photo["taken_at"]) - datetime.fromisoformat(photo["due_at"])
            late.append({"due": photo["due_at"], "taken": photo["taken_at"], "late_s": late_s.total_seconds()})
    return late


def schedule(experiment: dict) -> dict | None:
    """The running experiment's schedule, or None when it is not running on one."""
    sched = _running_schedule(experiment)
    if sched is None:
        return None
    progress = database.schedule_progress(experiment["id"], sched["since"])
    app_starts = database.app_starts(sched["since"])
    next_slot = max(_current_slot(sched, datetime.now(UTC)), progress["last_slot"]) + 1
    return {
        "interval_s": sched["interval_s"],
        "since": sched["since"],
        "next_photo_at": _due_at(sched, next_slot).isoformat(),
        "photos_taken": progress["photos_taken"],
        "photos_missed": progress["photos_missed"],
        "missed_by_reason": _missed_by_reason(progress["missed_reasons"]),
        "last_photo_due_at": progress["last_photo_due_at"],
        "downtime": _downtime(experiment["id"], sched["since"], app_starts),
        "late_photos": _late_photos(experiment["id"], sched["since"], app_starts),
    }


class Scheduler:
    """One background thread that takes the running experiment's scheduled photos."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at = datetime.now(UTC)

    def start(self) -> None:
        self._stop.clear()
        self._started_at = datetime.now(UTC)
        database.record_app_start(self._started_at.isoformat())
        self._thread = threading.Thread(target=self._run, name="scheduler", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout_s)

    def _run(self) -> None:
        wait_s = 0.0
        while not self._stop.wait(wait_s):
            try:
                wait_s = self._tick()
            except Exception:
                logger.exception("Scheduled capture failed; trying again")
                wait_s = CHECK_S

    def _tick(self) -> float:
        """Take the current slot's photo if it is not yet recorded. Returns seconds to wait."""
        experiment = database.running_experiment()
        sched = _running_schedule(experiment)
        if sched is None:
            return CHECK_S
        since = sched["since"]
        last_slot = database.schedule_progress(experiment["id"], since)["last_slot"]
        slot = _current_slot(sched, datetime.now(UTC))
        if slot > last_slot:
            # Slots that passed without a photo: due before this scheduler started, the app was
            # down; due since, the previous photo was still being taken (#62).
            slots = []
            for missed in range(last_slot + 1, slot):
                due = _due_at(sched, missed)
                reason = MISSED_APP_DOWN if due < self._started_at else MISSED_PHOTO_SLOW
                slots.append((missed, due.isoformat(), None, reason))
            due_at = _due_at(sched, slot).isoformat()
            try:
                # The app is shutting down: the camera may already be closing.
                if self._stop.is_set():
                    return 0.0
                array, record = captures.take_photo("capture")
                del array
                # Stop pressed while the photo was taken: it was saved as a rig photo.
                if (record["experiment"] or {}).get("id") == experiment["id"]:
                    slots.append((slot, due_at, record["capture_id"], None))
                else:
                    slots.append((slot, due_at, None, "experiment stopped during the photo"))
            except Exception as exc:
                logger.exception("Scheduled photo for slot %d failed", slot)
                slots.append((slot, due_at, None, str(exc) or "failed"))
            database.record_scheduled_photos(experiment["id"], since, slots)
            images.release_freed_memory()  # the photo's full-size frame is gone (#348)
            last_slot = slot
        wait_s = (_due_at(sched, last_slot + 1) - datetime.now(UTC)).total_seconds()
        return max(0.0, min(wait_s, CHECK_S))
