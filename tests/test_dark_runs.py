"""Nights in the Gallery (#419): which runs of lights-off photos collapse into one line.

A run collapses when it lasts 15 minutes or more (from its first photo to the next lit one),
wherever it falls in the day (Aaron, 2026-11-23 and 2026-11-24). The photo sequences are built
by hand, one minute apart unless a test says otherwise, so every answer can be counted off the
sequence without the code.
"""

from datetime import datetime, timedelta

import pytest

from npec_rig import dark_runs, database

pytestmark = pytest.mark.unit

DAY = datetime.fromisoformat("2026-11-16T00:00:00+00:00")
MINUTE = timedelta(minutes=1)


def _experiment(interval_s: float = 60) -> int:
    return database.create_experiment(uuid=f"e-{interval_s}", created_at=DAY.isoformat(), interval_s=interval_s)["id"]


def _photos(experiment_id: int, marks: list[str | None], *, start: datetime = DAY, every: timedelta = MINUTE) -> None:
    """One photo per mark, `every` apart from `start`, with that light mark saved."""
    rows = []
    for i, mark in enumerate(marks):
        taken = start + i * every
        capture_id = database.record_capture(
            taken_at=taken.isoformat(), path=f"experiments/e/{taken:%Y-%m-%d}/{taken:%H%M%S}_000000",
            purpose="capture", experiment_id=experiment_id, calibration=None, validation=None,
            lens_position=None, focus_locked_at=None, exposure_us=None, analogue_gain=None, flags=[],
        )
        rows.append({"capture_id": capture_id, "name": mark, "norm_e": None, "limit_fraction": None})
    database.record_exclusions(rows, worked_out_at=DAY.isoformat())


def _day(dark_from: int, dark_to: int) -> list[str | None]:
    """24 hours of photos a minute apart, lights off from minute `dark_from` to before `dark_to`."""
    return [("lights off" if dark_from <= m < dark_to else None) for m in range(24 * 60)]


def test_one_night_is_one_run() -> None:
    """Lights off 00:28 to 08:02 UTC, as in experiment 18: 454 photos, the last at 08:01."""
    experiment = _experiment()
    _photos(experiment, _day(28, 28 + 454))
    assert dark_runs.night_runs(experiment) == [
        {"start": "2026-11-16T00:28:00+00:00", "end": "2026-11-16T08:01:00+00:00", "photos": 454, "still_dark": False}
    ]


def test_a_dark_spell_under_15_minutes_stays_photos() -> None:
    """Day 1: a full night. Day 2: lights off only 02:00 to 02:14, 14 photos, 14 minutes."""
    experiment = _experiment()
    _photos(experiment, _day(28, 28 + 454) + _day(120, 134))
    assert [run["start"] for run in dark_runs.night_runs(experiment)] == ["2026-11-16T00:28:00+00:00"]


def test_a_dark_spell_in_the_day_collapses_too() -> None:
    """Two days with the night 00:28 to 08:02; on day 2 also lights off 14:00 to 14:20 (20 photos,
    20 minutes). Any dark run of 15 minutes or more collapses, wherever it falls (Aaron, 2026-11-24)."""
    experiment = _experiment()
    day_2 = [("lights off" if 14 * 60 <= m < 14 * 60 + 20 else mark) for m, mark in enumerate(_day(28, 482))]
    _photos(experiment, _day(28, 482) + day_2)
    assert [(run["start"], run["photos"]) for run in dark_runs.night_runs(experiment)] == [
        ("2026-11-16T00:28:00+00:00", 454), ("2026-11-17T00:28:00+00:00", 454), ("2026-11-17T14:00:00+00:00", 20)
    ]


def test_a_night_still_going_is_marked_still_dark() -> None:
    """A full day and night, then tonight's first 30 photos, 00:28 to 00:57: the newest photo is dark."""
    experiment = _experiment()
    _photos(experiment, _day(28, 482) + [None] * 28 + ["lights off"] * 30)
    assert dark_runs.night_runs(experiment)[-1] == {
        "start": "2026-11-17T00:28:00+00:00", "end": "2026-11-17T00:57:00+00:00", "photos": 30, "still_dark": True
    }


def test_three_photos_five_minutes_apart_are_15_minutes() -> None:
    """Photos every 5 minutes. Day 1: lights off 00:30 to 08:00. Day 2: lights off only 02:00,
    02:05 and 02:10, lit again at 02:15: 3 photos, 15 minutes."""
    experiment = _experiment(interval_s=300)
    day_1 = [("lights off" if 6 <= k < 96 else None) for k in range(288)]
    day_2 = [("lights off" if 24 <= k < 27 else None) for k in range(288)]
    _photos(experiment, day_1 + day_2, every=timedelta(minutes=5))
    assert [(run["start"], run["photos"]) for run in dark_runs.night_runs(experiment)] == [
        ("2026-11-16T00:30:00+00:00", 90), ("2026-11-17T02:00:00+00:00", 3)
    ]


def test_lamps_on_in_the_night_split_it_in_two() -> None:
    """Lights off 00:28 to 08:02, but lit 03:00 and 03:01 (Aaron's example, 2026-11-23)."""
    experiment = _experiment()
    night = [(None if m in (180, 181) else mark) for m, mark in enumerate(_day(28, 482))]
    _photos(experiment, night)
    assert [(run["start"], run["end"], run["photos"]) for run in dark_runs.night_runs(experiment)] == [
        ("2026-11-16T00:28:00+00:00", "2026-11-16T02:59:00+00:00", 152),
        ("2026-11-16T03:02:00+00:00", "2026-11-16T08:01:00+00:00", 300),
    ]


def test_an_unknown_experiment_is_a_lookup_error() -> None:
    with pytest.raises(LookupError):
        dark_runs.night_runs(999)


def test_an_experiment_with_no_lights_off_photos_has_no_nights() -> None:
    experiment = _experiment()
    _photos(experiment, [None] * 30)
    assert dark_runs.night_runs(experiment) == []
