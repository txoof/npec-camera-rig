"""Time lapse videos (#64): which photos become frames, what each frame says, the video job."""
from datetime import datetime, timedelta, timezone

import pytest

from npec_rig import database, timelapse
from tests.helpers import banded_validation

pytestmark = pytest.mark.unit

START = datetime(2027, 3, 1, 10, 0, tzinfo=timezone.utc)
# A tray outline and two cells in full-size photo pixels: enough for a frame to be drawn.
OUTLINE = [[100, 100], [400, 100], [400, 460], [100, 460]]


def _cell(name: str, holds: str, x: float, y: float, area: float | None) -> dict:
    return {"cell": name, "holds": holds, "centre_px": [x, y],
            "corners_px": [[x - 30, y - 30], [x + 30, y - 30], [x + 30, y + 30], [x - 30, y + 30]],
            "plant_px": None if area is None else 100, "area_mm2": area, "over_other_cells": False}


def _photo(experiment_id: int, taken: datetime, *, exclusion: str | None = None, tray_id: int = 4,
           warnings: list[str] | None = None, placement: str = "placed", area: float = 1000.0,
           grown_area: float | None = None, validation: str | None = None) -> int:
    """A photo of the experiment at `taken` with tray `tray_id` read in it, and its saved exclusion."""
    capture_id = database.record_capture(
        taken_at=taken.isoformat(), path=f"rig/{taken:%Y-%m-%d}/{taken:%H%M%S}_{taken:%f}", purpose="capture",
        experiment_id=experiment_id, calibration=None, validation=validation, lens_position=None,
        focus_locked_at=None, exposure_us=None, analogue_gain=None, flags=[],
    )
    database.record_tray_readings(capture_id, read_at=taken.isoformat(), status="read", trays=[{
        "tray_id": tray_id, "slot": None, "a1_corner": "SW", "placement": placement, "centre_px": [250, 280],
        "tilt_deg": 0.0, "margin_mm": None, "found": "photo + tag", "warnings": warnings or [],
        "outline_px": OUTLINE, "area_mm2": area, "segmenter": "green threshold, 0.1",
        **({} if grown_area is None else {"grown_method": "grow from leaf cores", "grown_area_mm2": grown_area}),
        "cells": [_cell("A1", "tag", 130, 430, None), _cell("B1", "plant", 190, 430, 250.0)],
    }])
    database.record_exclusions([{"capture_id": capture_id, "name": exclusion, "norm_e": None, "limit_fraction": None}],
                               worked_out_at=taken.isoformat())
    return capture_id


@pytest.fixture
def experiment() -> int:
    e = database.create_experiment(uuid="u-64", created_at=START.isoformat())
    database.start_experiment(e["id"], now=START.isoformat(), folder="experiments/x")
    return e["id"]


def test_each_hour_gives_its_first_usable_photo_and_counts_the_hours_without_one(experiment):
    m = timedelta(minutes=1)
    h = timedelta(hours=1)
    _photo(experiment, START, exclusion="light changing")
    first_good = _photo(experiment, START + m)
    _photo(experiment, START + 2 * m)
    # Hour 2: the tray's tag was seen but the tray was not: no frame, counted as skipped.
    _photo(experiment, START + h, warnings=["tag seen, tray not found in the photo"])
    # Hour 3: the lights were off. Night is not a skipped step.
    _photo(experiment, START + 2 * h, exclusion="lights off")
    _photo(experiment, START + 2 * h + m, exclusion="lights off")
    last_good = _photo(experiment, START + 3 * h + 30 * m)

    chosen = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 4 * h, per_hour=1)

    assert [f["capture"]["id"] for f in chosen["frames"]] == [first_good, last_good]
    assert chosen["skipped"] == 1


def test_two_frames_an_hour_take_one_photo_from_each_half_hour_inside_the_range_only(experiment):
    m = timedelta(minutes=1)
    _photo(experiment, START - m)  # before the range
    early = _photo(experiment, START + 5 * m)
    _photo(experiment, START + 20 * m)
    late = _photo(experiment, START + 31 * m)
    _photo(experiment, START + 60 * m)  # the end of the range is not in it

    chosen = timelapse.choose_frames(experiment, tray_id=4, start=START, end=START + 60 * m, per_hour=2)

    assert [f["capture"]["id"] for f in chosen["frames"]] == [early, late]
    assert chosen["skipped"] == 0


def _only_frame(experiment_id: int) -> dict:
    return timelapse.choose_frames(experiment_id, tray_id=4, start=START, end=START + timedelta(days=60), per_hour=1)["frames"][0]


def test_a_frame_says_utc_and_chamber_time_the_day_and_the_area_with_its_band(experiment):
    banded_validation("20270301T000000000000", {"North 1": ((250, 280), 2.0)})
    # 29 March 2027 is in summer time: the chamber is at UTC+2. Day 1 is the first 24 h.
    _photo(experiment, datetime(2027, 3, 29, 10, 0, tzinfo=timezone.utc), grown_area=1234.6,
           validation="20270301T000000000000")

    values = timelapse.frame_values(database.get_experiment(experiment), _only_frame(experiment), method="grown")

    assert values["utc"] == "2027-03-29 10:00 UTC"
    assert values["chamber"] == "12:00 chamber time"
    assert values["day"] == 29
    assert values["method"] == "Grow from leaf cores"
    assert values["area"] == "1,235 mm²"
    assert values["band"] == "±2.0%, North 1"


def test_a_frame_with_no_band_or_no_area_says_why_in_words(experiment):
    # 1 March 2027 is in winter time: UTC+1.
    _photo(experiment, START + timedelta(minutes=1), area=80.0)
    frame = _only_frame(experiment)

    fixed = timelapse.frame_values(database.get_experiment(experiment), frame, method="fixed")
    grown = timelapse.frame_values(database.get_experiment(experiment), frame, method="grown")

    assert fixed["chamber"] == "11:01 chamber time"
    assert fixed["day"] == 1
    assert fixed["area"] == "under 100 mm²"  # the fixed cutoff's floor (#288)
    assert fixed["band"] == "not validated"
    assert grown["area"] == "not worked out"
