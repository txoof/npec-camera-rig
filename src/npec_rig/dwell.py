"""Where on the chamber table each tray spends its time, and a warning when it stays too long in
one location (#332).

Light, temperature and airflow differ across the table, so a tray that stays in one location for a
long part of an experiment gets different conditions from the others. Researchers move trays to
even this out; this module tells them when a tray has stayed too long.

The table is divided into 6 locations, 3 columns by 2 rows: NW NM NE in the north row, SW SM SE in the
south row (north is up the photo, west is left). A tray's centre decides its location. These are
decisions, not measurements (Aaron, 2026-10-30, issue #332).
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from PIL import Image

from npec_rig import database
from npec_rig.calibration import TableFrame, build_table_frame
from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    CalibrationUnreadableError,
    calibration_frame_path,
    calibration_for_photos,
    load_saved_calibration,
    saved_calibration_path,
)
from npec_rig.captures import photo_file

LOCATIONS = ("NW", "NM", "NE", "SW", "SM", "SE")

# A tray counts as moved only after over this long found in another location, in a row: shorter stays, such
# as tray 1 beside its slot for 3 minutes on 28 October, are nudges. A decision, not a measurement
# (Aaron, 2026-10-30).
MOVE_AFTER = timedelta(hours=1)


def location_of(centre_px: tuple[float, float], photo_size: tuple[int, int], frame: TableFrame | None) -> str:
    """The table location a tray centred at `centre_px` (full-size photo pixels) lies in, in a
    photo of `photo_size` (width, height).

    With the calibration's table frame (the homography of the four corner tags), positions are
    worked out on the table, not in the photo: the rows meet halfway between the northern and the
    southern row of table tags, and the columns are thirds of the photo's width along the tray's
    own row of the table. Without a frame, in the photo: halves of its height, thirds of its width.
    """
    x, y = centre_px
    width, height = photo_size
    if frame is None:
        return ("N" if y < height / 2 else "S") + "WME"[min(max(int(3 * x / width), 0), 2)]
    u, v = frame.to_fraction(x, y)
    west, east = (_edge_u(_edge_ends(frame, edge_x, height), v) for edge_x in (0, width))
    column = int(3 * (u - west) / (east - west))
    return ("N" if v < 0.5 else "S") + "WME"[min(max(column, 0), 2)]


@lru_cache(maxsize=64)
def _edge_ends(frame: TableFrame, edge_x: float, height: int) -> tuple[tuple[float, float], tuple[float, float]]:
    """The photo's vertical edge at pixel column `edge_x`, top and bottom, on the table: the same
    for every tray in photos of one size and calibration, worked out once."""
    return frame.to_fraction(edge_x, 0), frame.to_fraction(edge_x, height)


def _edge_u(ends: tuple[tuple[float, float], tuple[float, float]], v: float) -> float:
    """Where the photo's vertical edge with these `ends` (`_edge_ends`) meets the table's row `v`,
    as the table's `u`. The edge is a straight line on the table too: a homography keeps lines
    straight."""
    (u0, v0), (u1, v1) = ends
    return u0 + (u1 - u0) * (v - v0) / (v1 - v0)


@dataclass(frozen=True)
class Stay:
    """One run of a tray in one location: from the first photo it was found there to the last."""

    location: str
    start: datetime
    end: datetime


def stays(readings: Iterable[tuple[datetime, str]]) -> list[Stay]:
    """One tray's stays, oldest first, from its readings: (time, location) for each read photo the tray
    was found in. A photo the tray was not found in has no reading: misses and the tray taken off
    the table for up to `database.NOT_SEEN_FOR` do not break a stay; missing longer, it was taken
    away, its stay ended at its last photo and it starts a new one when found again, even in the
    same location (Aaron, 2026-10-30). A tray found in another location starts a new stay only
    once it has been away from its stay's location for over `MOVE_AFTER`, from its first photo
    elsewhere to the last, in any other locations together (a centre on the line between two of
    them flips between both); it is then in the one of them it was in longest (each photo counting
    until the next), from its first photo away. A shorter time away is part of the stay it left and
    came back to."""
    out: list[Stay] = []
    away: list[tuple[datetime, str]] = []  # readings anywhere else since the last one in out[-1].location
    last: datetime | None = None
    for taken_at, location in sorted(readings):
        # Missing over NOT_SEEN_FOR, it was taken away: its stay ended at its last photo.
        gone = last is not None and taken_at - last > database.NOT_SEEN_FOR
        last = taken_at
        if not out or gone:
            out.append(Stay(location, taken_at, taken_at))
            away = []
        elif location == out[-1].location:
            out[-1] = Stay(location, out[-1].start, taken_at)
            away = []
        else:
            away.append((taken_at, location))
            if taken_at - away[0][0] > MOVE_AFTER:
                out.append(Stay(_most_time(away), away[0][0], taken_at))
                away = []
    return out


def _most_time(readings: list[tuple[datetime, str]]) -> str:
    """The location of `readings` (oldest first) the tray was in longest, each reading counting
    until the next; on a tie, the one found last."""
    time: dict[str, timedelta] = {}
    for (taken_at, location), (following, _next) in zip(readings, readings[1:]):
        time[location] = time.get(location, timedelta()) + following - taken_at
    time.setdefault(readings[-1][1], timedelta())
    order = {location: i for i, (_t, location) in enumerate(readings)}
    return max(time, key=lambda location: (time[location], order[location]))


class LocationFinder:
    """The location of each tray in photos read with their calibration (`location_of`), each calibration's
    table frame and photo size looked up once. Photos taken under one calibration are taken in one
    camera mode, so the first photo found gives the size of all; with none on disk, the
    calibration's own photo. Make one per question: a calibration can be rebuilt in the meantime."""

    def __init__(self) -> None:
        self._frames: dict[str | None, TableFrame | None] = {}
        self._sizes: dict[str | None, tuple[int, int]] = {}

    def location(self, path: str, calibration: str | None, centre_px: tuple[float, float]) -> str | None:
        """The location of a tray centred at `centre_px` in photo `path`, taken under `calibration`;
        None when the photo's size cannot be known (neither it nor its calibration's photo is on
        disk)."""
        size = self._size(path, calibration)
        return None if size is None else location_of(centre_px, size, self._frame(calibration))

    def _frame(self, calibration: str | None) -> TableFrame | None:
        if calibration not in self._frames:
            self._frames[calibration] = _table_frame(calibration)
        return self._frames[calibration]

    def _size(self, path: str, calibration: str | None) -> tuple[int, int] | None:
        if calibration not in self._sizes:
            files = [photo_file(path)]
            if calibration is not None:
                files.append(calibration_frame_path(calibration))
            for file in files:
                if file is not None and file.exists():
                    with Image.open(file) as image:
                        self._sizes[calibration] = image.size
                    break
        return self._sizes.get(calibration)


def _table_frame(calibration: str | None) -> TableFrame | None:
    """The table frame of the calibration photos taken under `calibration` are read with, from
    its four corner tags; None without a calibration or four corner tags."""
    if calibration is None:
        return None
    try:
        baseline = load_saved_calibration(calibration_for_photos(calibration)).corner_baseline
        return None if baseline is None else build_table_frame(baseline)
    except (CalibrationNotFoundError, CalibrationUnreadableError, ValueError):
        return None


# Each experiment's readings, with the key they were worked out for: the pages ask again every few
# seconds, and an experiment of 8 days (about 100 000 readings) takes seconds to work out. Requests
# run in threads: the lock lets one rebuild while the others wait for it, not all rebuild at once.
_readings_cache: dict[int, tuple[tuple, list[tuple[int, str, datetime, str]]]] = {}
_readings_lock = threading.Lock()


def _calibrations_key(experiment_id: int) -> tuple:
    """Which calibration each of the experiment's calibrations is read with now, and that file's
    time: a rebuilt twin (`calibration_for_photos`) or a changed file changes it."""
    key = []
    for stem in database.experiment_calibrations(experiment_id):
        if stem is None:
            key.append((None, None, None))
            continue
        used = calibration_for_photos(stem)
        try:
            mtime = saved_calibration_path(used).stat().st_mtime_ns
        except (CalibrationNotFoundError, OSError):
            mtime = None
        key.append((stem, used, mtime))
    return tuple(key)


def _experiment_readings(experiment_id: int, until: str | None = None) -> dict[int, list[tuple[datetime, str]]]:
    """Each tray's readings in the experiment's read photos taken up to `until` (all with None):
    (time, location), oldest first. A tray whose location cannot be known in a photo is left out of it.
    Worked out again whenever a photo of the experiment is read or read again, or a calibration
    its photos are read with changes."""
    with _readings_lock:
        key = (database.experiment_tray_reads_mark(experiment_id), _calibrations_key(experiment_id))
        cached = _readings_cache.get(experiment_id)
        if cached is None or cached[0] != key:
            finder = LocationFinder()
            everything: list[tuple[int, str, datetime, str]] = []
            for p in database.experiment_tray_positions(experiment_id):
                location = finder.location(p["path"], p["calibration"], p["centre_px"])
                if location is not None:
                    everything.append((p["tray_id"], p["taken_at"], datetime.fromisoformat(p["taken_at"]), location))
            cached = _readings_cache[experiment_id] = (key, everything)
    readings: dict[int, list[tuple[datetime, str]]] = {}
    for tray_id, taken_at, when, location in cached[1]:
        if until is None or taken_at <= until:
            readings.setdefault(tray_id, []).append((when, location))
    return readings


def tray_stays(experiment_id: int, until: str | None = None) -> dict[int, list[Stay]]:
    """Each tray's stays (`stays`) in the experiment's read photos taken up to `until` (UTC; all
    with None), oldest first, by tray ID: for the diagrams on the Experiments page."""
    return {tray_id: stays(readings) for tray_id, readings in sorted(_experiment_readings(experiment_id, until).items())}


def _hours(stay: Stay) -> float:
    return (stay.end - stay.start) / timedelta(hours=1)


def over_limit(experiment_id: int, at: str) -> list[dict]:
    """The experiment's trays that, at time `at` (UTC), have stayed in one location for its dwell
    limit (`experiment.dwell_limit_h`) or longer, in tray ID order: tray ID, the location, since when
    and for how many hours, from the stay's first photo to `at`. A tray missing for up to
    `database.NOT_SEEN_FOR` still counts in its location; missing longer, it was taken away, and is
    not warned for until it is found again (Aaron, 2026-10-30, #331's rule). A tray hidden on the
    experiment's panel, such as a misread tag, is never warned for (Aaron, 2026-11-02)."""
    limit_h = database.get_experiment(experiment_id)["dwell_limit_h"]
    hidden = database.hidden_trays(experiment_id)
    now = datetime.fromisoformat(at)
    out = []
    for tray_id, readings in sorted(_experiment_readings(experiment_id, until=at).items()):
        if tray_id in hidden:
            continue
        stay = stays(readings)[-1]
        if now - readings[-1][0] > database.NOT_SEEN_FOR:
            continue
        hours = (now - stay.start) / timedelta(hours=1)
        if hours >= limit_h:
            out.append({"tray_id": tray_id, "location": stay.location, "since": stay.start.isoformat(), "hours": hours})
    return out


def hours_per_location(experiment_id: int, until: str | None = None) -> dict[int, dict[str, float]]:
    """Each tray's hours in each location (`LOCATIONS`, every one, 0 where it never stayed) over the
    experiment, up to `until` (UTC; all with None), by tray ID: each stay from its first to its
    last photo. The minutes between a stay's last photo and the next stay's first are in neither,
    nor are nudges a stay of their own: they count in the stay they interrupted."""
    out = {}
    for tray_id, tray in tray_stays(experiment_id, until).items():
        hours = dict.fromkeys(LOCATIONS, 0.0)
        for stay in tray:
            hours[stay.location] += _hours(stay)
        out[tray_id] = hours
    return out
