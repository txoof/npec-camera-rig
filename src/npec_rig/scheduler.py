"""Scheduled capture: a photo every interval while an experiment runs (M3, issue #60).

Photo times are counted from the schedule's start in UTC (the latest start, resume or interval
change, `experiment.schedule_since`), not from the last photo, so the next one is known after a
restart and for any interval (a minute, an hour, a day). Slot n is due n intervals after it. Every slot is recorded in `rig.db` as taken or missed, so a
restart resumes after the last recorded slot and counts the slots that passed while it was down.
"""

import bisect
import logging
import math
import threading
from datetime import UTC, datetime, timedelta

from npec_rig import captures, database, images, settings

logger = logging.getLogger(__name__)

# The shortest interval accepted: a full-resolution still takes about 3 s (issue #43). The page
# offers 1 to 6 minutes.
MIN_INTERVAL_S = 10.0

# The longest the loop sleeps before looking at the running experiment again, so a start or stop
# is noticed within this time whatever the interval.
CHECK_S = 1.0
MISSED_APP_DOWN = "the app was not running"
# A slot whose photo was saved while rig.db could not be written, and then not found on disk to be
# added (#439): moved or deleted by hand.
MISSED_NOT_FOUND = "the photo was saved but could not be found to add to the database"
MISSED_PHOTO_SLOW = "the previous photo took longer than the interval"
# A slot that passed while rig.db could not be written: the previous photo waited for the lock
# (#481, Aaron 2026-11-23).
MISSED_DB_LOCKED = "rig.db could not be written"
# A slot whose photo is on disk but whose info file could not be read (empty or damaged, as after a
# power cut), so the photo could not be added to the database (#481, Aaron 2026-11-23).
MISSED_RECORD_UNREADABLE = "the photo was saved but its record could not be read"


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
    """Missed photos counted as app down, photo slow, rig.db locked, or photo failed (any other
    reason: the error the camera gave)."""
    app_down = reasons.get(MISSED_APP_DOWN, 0)
    photo_slow = reasons.get(MISSED_PHOTO_SLOW, 0)
    db_locked = reasons.get(MISSED_DB_LOCKED, 0)
    return {
        "app_down": app_down,
        "photo_slow": photo_slow,
        "db_locked": db_locked,
        "photo_failed": sum(reasons.values()) - app_down - photo_slow - db_locked,
    }


def _downtime(experiment_id: int, since: str, app_starts: list[str]) -> list[dict]:
    """Each time the app was down during the schedule: from the last photo taken before it came
    back (or the schedule's start) until it came back. When it went down is not known."""
    periods = []
    for started_at in app_starts:
        last = database.last_photo_taken_at(experiment_id, started_at)
        after = since if last is None else max(since, last)
        periods.append({"after": after, "until": started_at})
    return periods


def _late_photos(experiment_id: int, since: str, app_starts: list[str]) -> list[dict]:
    """Photos due while the app was down and taken when it came back, with how late."""
    late = []
    starts = sorted(app_starts)
    for photo in database.scheduled_photos_taken(experiment_id, since):
        # The first start after the photo was due: late when the app started before it was taken.
        first = bisect.bisect_right(starts, photo["due_at"])
        if first < len(starts) and starts[first] <= photo["taken_at"]:
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
        # Slots not yet written to rig.db, which was locked, oldest first: (experiment id,
        # schedule since, slots). Written after a later photo, and counted as recorded meanwhile,
        # so no slot's photo is taken twice (#439, #481).
        self._unwritten: list[tuple[int, str, list]] = []
        # When the last photo's database work began, after its camera work: slots due from then
        # until the next photo were lost to rig.db, not to a slow camera (#481).
        self._database_since: datetime | None = None
        # Photos saved while rig.db was locked may still need their rows; also true at start, for
        # slots left so by an earlier run (#439).
        self._settle_due = True
        # Work done once after a start, never before the first photo (#489): the rows of photos
        # saved before it without one, in every experiment; and the slots those photos' info files
        # name, which the schedule has not recorded.
        self._adopt_all_due = True
        self._recover_slots_due = True

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
        # Stopping (the app shuts down): one last try to write the slots not yet written (#481).
        if self._unwritten:
            self._catch_up(None)

    def _recover_slots(self, experiment: dict, sched: dict) -> None:
        """Slots whose photo was saved before this start but never written to rig.db (the app
        stopped while rig.db was locked, #489): their info files name them. They are queued to be
        written like any slot, after the photo, for the photos to be linked, and the slots
        between them, lost to the lock, say so. Without this the gap is counted "the app was not
        running", though the photos exist. The slot of a photo of the current interval is
        counted too, so that slot's photo is not taken twice."""
        last_slot = max(
            database.schedule_progress(experiment["id"], sched["since"])["last_slot"],
            self._last_unwritten_slot(experiment["id"], sched["since"]),
        )
        named = captures.scheduled_slots_on_disk(
            experiment, sched["since"], from_day=_due_at(sched, last_slot).date().isoformat()
        )
        named = {slot: due for slot, due in named.items() if slot > last_slot}
        if not named:
            return
        self._unwritten.append((experiment["id"], sched["since"], [
            (slot, named[slot], None, None) if slot in named
            else (slot, _due_at(sched, slot).isoformat(), None, MISSED_DB_LOCKED)
            for slot in range(last_slot + 1, max(named) + 1)
        ]))
        self._settle_due = True  # the photos are linked to these slots next

    def _tick(self) -> float:
        """Take the current slot's photo if it is not yet recorded, then do the database work.
        Returns seconds to wait.

        The photo comes first: nothing the database does stops it (#481, Aaron 2026-11-23). While
        rig.db is locked, each photo is still taken and saved with its info file; its row and
        slot are added after the lock ends."""
        experiment = database.running_experiment()
        sched = _running_schedule(experiment)
        if sched is None:
            # Stopped with slots not yet written: write them now, no photo is waiting (#481).
            if self._unwritten:
                self._catch_up(None)
            elif self._adopt_all_due:
                self._adopt_everything()  # no schedule to keep: nothing waits for it (#489)
            return CHECK_S
        since = sched["since"]
        if self._recover_slots_due:
            try:
                self._recover_slots(experiment, sched)
                self._recover_slots_due = False
            except Exception:
                logger.exception("Could not read the slots of the photos already on disk; trying again")
        last_slot = max(
            database.schedule_progress(experiment["id"], since)["last_slot"],
            self._last_unwritten_slot(experiment["id"], since),
        )
        slot = _current_slot(sched, datetime.now(UTC))
        if slot > last_slot:
            # Slots that passed without a photo: due before this scheduler started, the app was
            # down; due since, the previous photo was still being taken (#62), or, once its camera
            # work was done, its database work was waiting for rig.db (#481).
            slots = []
            for missed in range(last_slot + 1, slot):
                due = _due_at(sched, missed)
                if due < self._started_at:
                    reason = MISSED_APP_DOWN
                elif self._database_since is not None and due >= self._database_since:
                    reason = MISSED_DB_LOCKED
                else:
                    reason = MISSED_PHOTO_SLOW
                slots.append((missed, due.isoformat(), None, reason))
            due_at = _due_at(sched, slot).isoformat()
            row_failed = False
            try:
                # The app is shutting down: the camera may already be closing.
                if self._stop.is_set():
                    return 0.0
                # The slot goes into the photo's info file, so a row added later is linked to
                # its slot by name, not by when the photo was taken (#488).
                schedule = {"since": since, "slot": slot, "due_at": due_at}
                array, record = captures.take_photo("capture", extra={"schedule": schedule})
                del array
                self._database_since = datetime.now(UTC) - timedelta(seconds=record.get("database_s", 0.0))
                # Stop pressed while the photo was taken: it was saved as a rig photo.
                if (record["experiment"] or {}).get("id") == experiment["id"]:
                    slots.append((slot, due_at, record["capture_id"], None))
                    row_failed = record["capture_id"] is None
                else:
                    slots.append((slot, due_at, None, "experiment stopped during the photo"))
            except Exception as exc:
                self._database_since = datetime.now(UTC)
                logger.exception("Scheduled photo for slot %d failed", slot)
                slots.append((slot, due_at, None, str(exc) or "failed"))
            self._unwritten.append((experiment["id"], since, slots))
            images.release_freed_memory()  # the photo's full-size frame is gone (#348)
            last_slot = slot
            # The photo's own row just failed (rig.db locked): every write would wait as long
            # again, so the rest is tried later.
            if row_failed:
                self._settle_due = True
            else:
                self._catch_up(experiment)
        wait_s = (_due_at(sched, last_slot + 1) - datetime.now(UTC)).total_seconds()
        # Between photos, the database work still to do is tried when a full wait for a lock
        # fits before the next photo, so it can never delay it (#481).
        if (self._unwritten or self._settle_due) and wait_s > settings.LOCK_WAIT_S + CHECK_S:
            self._database_since = datetime.now(UTC)
            self._catch_up(experiment)
            wait_s = (_due_at(sched, last_slot + 1) - datetime.now(UTC)).total_seconds()
        return max(0.0, min(wait_s, CHECK_S))

    def _last_unwritten_slot(self, experiment_id: int, since: str) -> int:
        return max(
            (s[0] for eid, s_since, slots in self._unwritten if (eid, s_since) == (experiment_id, since) for s in slots),
            default=0,
        )

    def _catch_up(self, experiment: dict | None) -> None:
        """The database work after a photo: write the slots not yet written, oldest first, then,
        for a running `experiment`, add and link the photos saved while rig.db was locked. A
        failure is logged and tried again later; it never stops a photo (#481)."""
        try:
            while self._unwritten:
                database.record_scheduled_photos(*self._unwritten[0])
                self._unwritten.pop(0)
            if experiment is not None:
                self._adopt_everything()
                self._settle_unlinked(experiment)
                self._settle_due = False
        except Exception:
            self._settle_due = True
            logger.exception("Could not write to rig.db after the photo; trying again later")

    def _adopt_everything(self) -> None:
        """Once after a start: add the rows of photos in every experiment that lack one (#489).
        Raises while rig.db is locked, and is tried again at the next catch-up."""
        if self._adopt_all_due:
            captures.adopt_all_unrecorded_photos()
            self._adopt_all_due = False

    @staticmethod
    def _settle_unlinked(experiment: dict) -> None:
        """Slots whose photo was saved while rig.db was locked (#439): add the photos to rig.db
        and link them. Raises, to be tried on the next tick, while rig.db is still locked."""
        unlinked = database.unlinked_slots(experiment["id"])
        if not unlinked:
            return
        # Every day from the oldest slot's due time to now: a photo may be saved long after its
        # slot was due, across UTC midnight too (#488).
        today = datetime.now(UTC).date()
        day = datetime.fromisoformat(unlinked[0]["due_at"]).date()  # oldest first
        days = set()
        while day <= today:
            days.add(day.isoformat())
            day += timedelta(days=1)
        adopted = captures.adopt_unrecorded_photos(experiment, days)
        database.link_unlinked_slots(
            experiment["id"], experiment["interval_s"], not_found=MISSED_NOT_FOUND,
            photo_paths=adopted.slots,
            unreadable=adopted.unreadable, unreadable_reason=MISSED_RECORD_UNREADABLE,
        )
