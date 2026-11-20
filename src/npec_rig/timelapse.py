"""Time lapse videos of a tray or a cell over an experiment (#64).

The plan is in issue #64 (2026-11-20). Nothing is segmented again: each frame is drawn from a
photo and what its reading stored (outline, cells, areas, masks), and its numbers are those of
`tray_readings.capture_readings`, the same the Gallery shows.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from npec_rig import database, dwell, tray_readings

# Rig times are UTC; the chamber keeps Dutch local time (CLAUDE.md).
CHAMBER_TIME = ZoneInfo("Europe/Amsterdam")
# Frames per hour a request may ask for (Aaron, 2026-11-20).
PER_HOUR = (1, 2, 5)
# A tray with one of these is not where its reading says, or is not one tray (the trial of
# 2026-11-17, #64).
_NOT_USABLE = {"no tag", "tag seen, tray not found in the photo", "two tags in one tray outline"}


def _step(taken_at: str, per_hour: int) -> tuple:
    """The step of the clock a photo falls in: steps of 60 / per_hour minutes from each UTC hour."""
    t = datetime.fromisoformat(taken_at)
    return t.date(), t.hour, t.minute * per_hour // 60


def usable_tray(readings: dict | None, tray_id: int) -> dict | None:
    """Tray `tray_id` of a photo's readings (`capture_readings`) when a frame can be made of it:
    the photo has no exclusion, and the tray is placed by its own tag with an outline and cells.
    None otherwise."""
    if readings is None or readings["status"] != "read" or readings["exclusion"] is not None:
        return None
    trays = [t for t in readings["trays"] if t["tray_id"] == tray_id]
    if len(trays) != 1:
        return None
    tray = trays[0]
    if (tray["placement"] != "placed" or not tray["outline_px"] or not tray["cells"] or tray["not_counted"]
            or _NOT_USABLE & set(tray["warnings"])):
        return None
    return tray


def choose_frames(experiment_id: int, *, tray_id: int, start: datetime, end: datetime, per_hour: int) -> dict:
    """The photos of tray `tray_id` that become frames, from `start` up to `end`: in each step of
    the clock (`per_hour` steps an hour), the first photo with a usable tray (`usable_tray`).
    `frames`: one dict per frame, oldest first, with the photo's `capture` row, its `readings` and
    the `tray`. `skipped`: the steps that had photos but none usable, not counting steps with the
    lights off in every photo."""
    if per_hour not in PER_HOUR:
        raise ValueError(f"per_hour must be one of {PER_HOUR}")
    captures = {c["id"]: c for c in database.captures_for_experiment(experiment_id)}
    first, last = start.isoformat(), end.isoformat()
    by_step: dict[tuple, list[dict]] = {}
    for p in database.experiment_tray_positions(experiment_id):
        if p["tray_id"] == tray_id and first <= p["taken_at"] < last:
            by_step.setdefault(_step(p["taken_at"], per_hour), []).append(captures[p["capture_id"]])
    locations = dwell.LocationFinder()
    frames, skipped = [], 0
    for step in sorted(by_step):
        dark = True
        for capture in by_step[step]:
            readings = tray_readings.capture_readings(capture, history=False, locations=locations)
            tray = usable_tray(readings, tray_id)
            if tray is not None:
                frames.append({"capture": capture, "readings": readings, "tray": tray})
                break
            dark = dark and readings is not None and readings["exclusion"] == "lights off"
        else:
            skipped += 0 if dark else 1
    return {"frames": frames, "skipped": skipped}


def frame_values(experiment: dict, frame: dict, *, method: str) -> dict:
    """What frame `frame` (from `choose_frames`) of `experiment` says, in the Gallery's words: the
    time in UTC and in chamber time, the day of the experiment (day 1 is its first 24 h), the area
    method's name, the tray's plant area by it, and the band of the tray's slot or the reason there
    is none. `method` is the key of one of `tray_readings.AREA_METHODS`."""
    m = next(m for m in tray_readings.AREA_METHODS if m["key"] == method)
    taken = datetime.fromisoformat(frame["capture"]["taken_at"])
    started = datetime.fromisoformat(experiment["periods"][0]["started_at"])
    tray = frame["tray"]
    area = tray[m["area"]]
    floor = tray[m["floor"]] if m["floor"] else None
    if area is None:
        area_text = "not worked out"
    elif floor is not None and area < floor:
        area_text = f"under {floor} mm²"
    else:
        area_text = f"{round(area):,} mm²"
    band = tray["uncertainty"]
    band_text = f"±{band['band_pct']:.1f}%, {band['slot']}" if band["band_pct"] is not None else band["reason"]
    return {
        "utc": f"{taken:%Y-%m-%d %H:%M} UTC",
        "chamber": f"{taken.astimezone(CHAMBER_TIME):%H:%M} chamber time",
        "day": (taken - started).days + 1,
        "tray_id": tray["tray_id"],
        "method": m["name"],
        "area": area_text,
        "band": band_text,
    }
