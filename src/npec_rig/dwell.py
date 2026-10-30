"""Where on the chamber table each tray spends its time, and a warning when it stays too long in
one area (#332).

Light, temperature and airflow differ across the table, so a tray that stays in one area for a
long part of an experiment gets different conditions from the others. Researchers move trays to
even this out; this module tells them when a tray has stayed too long.

The table is divided into 6 areas, 3 columns by 2 rows: NW NM NE in the north row, SW SM SE in the
south row (north is up the photo, west is left). A tray's centre decides its area. These are
decisions, not measurements (Aaron, 2026-10-30, issue #332).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from PIL import Image

from npec_rig import database
from npec_rig.calibration import TableFrame, build_table_frame
from npec_rig.calibration_store import (
    CalibrationNotFoundError,
    CalibrationUnreadableError,
    calibration_frame_path,
    calibration_for_photos,
    load_saved_calibration,
)
from npec_rig.captures import photo_file

AREAS = ("NW", "NM", "NE", "SW", "SM", "SE")

# A tray counts as moved only after this long found in another area, in a row: shorter stays, such
# as tray 1 beside its slot for 3 minutes on 28 October, are nudges. A decision, not a measurement
# (Aaron, 2026-10-30).
MOVE_AFTER = timedelta(hours=1)


def area_of(centre_px: tuple[float, float], photo_size: tuple[int, int], frame: TableFrame | None) -> str:
    """The area of the table a tray centred at `centre_px` (full-size photo pixels) lies in, in a
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
    west, east = (_edge_u(frame, edge_x, height, v) for edge_x in (0, width))
    column = int(3 * (u - west) / (east - west))
    return ("N" if v < 0.5 else "S") + "WME"[min(max(column, 0), 2)]


def _edge_u(frame: TableFrame, edge_x: float, height: int, v: float) -> float:
    """Where the photo's vertical edge at pixel column `edge_x` meets the table's row `v`, as the
    table's `u`. The edge is a straight line on the table too: a homography keeps lines straight."""
    (u0, v0), (u1, v1) = frame.to_fraction(edge_x, 0), frame.to_fraction(edge_x, height)
    return u0 + (u1 - u0) * (v - v0) / (v1 - v0)


@dataclass(frozen=True)
class Stay:
    """One run of a tray in one area: from the first photo it was found there to the last."""

    area: str
    start: datetime
    end: datetime


def stays(readings: Iterable[tuple[datetime, str]]) -> list[Stay]:
    """One tray's stays, oldest first, from its readings: (time, area) for each read photo the tray
    was found in. A photo the tray was not found in has no reading: misses and the tray taken off
    the table for a while do not break a stay. A tray found in another area starts a new stay only
    once it has been found there for `MOVE_AFTER`, from the first to the last photo in a row; it is
    then in the new area from its first photo there. A shorter stay elsewhere is part of the stay
    it left and came back to."""
    out: list[Stay] = []
    away: list[tuple[datetime, str]] = []  # readings elsewhere since the last one in out[-1].area
    for taken_at, area in sorted(readings):
        if not out:
            out.append(Stay(area, taken_at, taken_at))
        elif area == out[-1].area:
            out[-1] = Stay(area, out[-1].start, taken_at)
            away = []
        else:
            away = [r for r in away if r[1] == area] + [(taken_at, area)]
            if taken_at - away[0][0] >= MOVE_AFTER:
                out.append(Stay(area, away[0][0], taken_at))
                away = []
    return out


class AreaFinder:
    """The area of each tray in photos read with their calibration (`area_of`), each calibration's
    table frame and photo size looked up once. Photos taken under one calibration are taken in one
    camera mode, so the first photo found gives the size of all; with none on disk, the
    calibration's own photo. Make one per question: a calibration can be rebuilt in the meantime."""

    def __init__(self) -> None:
        self._frames: dict[str | None, TableFrame | None] = {}
        self._sizes: dict[str | None, tuple[int, int]] = {}

    def area(self, path: str, calibration: str | None, centre_px: tuple[float, float]) -> str | None:
        """The area of a tray centred at `centre_px` in photo `path`, taken under `calibration`;
        None when the photo's size cannot be known (neither it nor its calibration's photo is on
        disk)."""
        size = self._size(path, calibration)
        return None if size is None else area_of(centre_px, size, self._frame(calibration))

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


def _experiment_readings(experiment_id: int, until: str | None = None) -> dict[int, list[tuple[datetime, str]]]:
    """Each tray's readings in the experiment's read photos taken up to `until` (all with None):
    (time, area), oldest first. A tray whose area cannot be known in a photo is left out of it."""
    finder = AreaFinder()
    readings: dict[int, list[tuple[datetime, str]]] = {}
    for p in database.experiment_tray_positions(experiment_id):
        if until is not None and p["taken_at"] > until:
            continue
        area = finder.area(p["path"], p["calibration"], p["centre_px"])
        if area is not None:
            readings.setdefault(p["tray_id"], []).append((datetime.fromisoformat(p["taken_at"]), area))
    return readings


def _hours(stay: Stay) -> float:
    return (stay.end - stay.start) / timedelta(hours=1)


def over_limit(experiment_id: int, at: str) -> list[dict]:
    """The experiment's trays that, at time `at` (UTC), have stayed in one area for its dwell
    limit (`experiment.dwell_limit_h`) or longer, in tray ID order: tray ID, the area, since when
    and for how many hours, from the first to the last photo of the stay taken by then."""
    limit_h = database.get_experiment(experiment_id)["dwell_limit_h"]
    out = []
    for tray_id, readings in sorted(_experiment_readings(experiment_id, until=at).items()):
        stay = stays(readings)[-1]
        if _hours(stay) >= limit_h:
            out.append({"tray_id": tray_id, "area": stay.area, "since": stay.start.isoformat(), "hours": _hours(stay)})
    return out
