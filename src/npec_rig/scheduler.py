"""Scheduled capture: a photo every interval while an experiment runs (M3, issue #60).

Photo times are counted from the start of the running period, in UTC, not from the last photo, so
the next one is known after a restart and for any interval (a minute, an hour, a day). Slot n is
due n intervals after the start. Every slot is recorded in `rig.db` as taken or missed, so a
restart resumes after the last recorded slot and counts the slots that passed while it was down.
"""

import logging
import math
import threading
from datetime import UTC, datetime, timedelta

from npec_rig import captures, database

logger = logging.getLogger(__name__)

# The longest the loop sleeps before looking at the running experiment again, so a start or stop
# is noticed within this time whatever the interval.
CHECK_S = 1.0


def _running_period(experiment: dict | None) -> dict | None:
    period = experiment["periods"][-1] if experiment and experiment["periods"] else None
    if period is None or period["ended_at"] is not None or not period["interval_s"]:
        return None
    return period


def _due_at(period: dict, slot: int) -> datetime:
    started = datetime.fromisoformat(period["started_at"])
    return started + timedelta(seconds=slot * period["interval_s"])


def _current_slot(period: dict, now: datetime) -> int:
    elapsed_s = (now - datetime.fromisoformat(period["started_at"])).total_seconds()
    return math.floor(elapsed_s / period["interval_s"])


def schedule(experiment: dict) -> dict | None:
    """The running period's schedule, or None when the experiment is not running on one."""
    period = _running_period(experiment)
    if period is None:
        return None
    progress = database.schedule_progress(experiment["id"], period["started_at"])
    next_slot = max(_current_slot(period, datetime.now(UTC)), progress["last_slot"]) + 1
    return {
        "interval_s": period["interval_s"],
        "next_photo_at": _due_at(period, next_slot).isoformat(),
        "photos_taken": progress["photos_taken"],
        "photos_missed": progress["photos_missed"],
        "last_photo_due_at": progress["last_photo_due_at"],
    }


class Scheduler:
    """One background thread that takes the running experiment's scheduled photos."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
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
        period = _running_period(experiment)
        if period is None:
            return CHECK_S
        started_at = period["started_at"]
        last_slot = database.schedule_progress(experiment["id"], started_at)["last_slot"]
        slot = _current_slot(period, datetime.now(UTC))
        if slot > last_slot:
            # Slots that passed without a photo: the app was down, or a photo took too long.
            slots = [
                (missed, _due_at(period, missed).isoformat(), None, "not taken in time")
                for missed in range(last_slot + 1, slot)
            ]
            try:
                array, record = captures.take_photo("capture")
                del array
                slots.append((slot, _due_at(period, slot).isoformat(), record["capture_id"], None))
            except Exception as exc:
                logger.exception("Scheduled photo for slot %d failed", slot)
                slots.append((slot, _due_at(period, slot).isoformat(), None, str(exc) or "failed"))
            database.record_scheduled_photos(experiment["id"], started_at, slots)
            last_slot = slot
        wait_s = (_due_at(period, last_slot + 1) - datetime.now(UTC)).total_seconds()
        return max(0.0, min(wait_s, CHECK_S))
