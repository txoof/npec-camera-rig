"""Tests for analysis.py, the Round 2 run's analysis (metrology log 16). Expected values are worked
by hand from the rules in 16.3 and 16.4, not by the code's own arithmetic.

    cd experiments/round2-run && PYTHONPATH=../../src python -m pytest test_analysis.py
"""

from datetime import UTC, datetime, timedelta

import pytest

import analysis

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 22, 18, 0, tzinfo=UTC)


def photo(minute, **changes):
    """A photo `minute` minutes after T0 that passes every rule of 16.3 unless changed."""
    record = {
        "capture_id": minute, "taken_at": T0 + timedelta(minutes=minute), "status": "read",
        "calibration": "C1", "lens_position": 6.05, "flags": [], "app_up_s": 10_000.0 + 60 * minute,
    }
    record.update(changes)
    return record


def test_a_pair_one_minute_apart_with_nothing_between_is_undisturbed():
    pairs = analysis.pairs([photo(0), photo(1)], breaks=[], camera_events=[])
    assert [(p["before"], p["after"], p["reason"]) for p in pairs] == [(0, 1, None)]


@pytest.mark.parametrize("start_s, end_s", [(30, 30), (-600, 30), (30, 600), (60, 60)])
def test_a_shuffle_or_event_between_the_photos_disturbs_the_pair(start_s, end_s):
    # A break overlapping the time after the first photo, up to and including the second.
    pairs = analysis.pairs(
        [photo(0), photo(1)],
        breaks=[(T0 + timedelta(seconds=start_s), T0 + timedelta(seconds=end_s))],
        camera_events=[],
    )
    assert pairs[0]["reason"] == "shuffle or event"


def test_a_break_that_ended_at_the_first_photo_leaves_the_pair_undisturbed():
    pairs = analysis.pairs([photo(0), photo(1)], breaks=[(T0 - timedelta(minutes=5), T0)], camera_events=[])
    assert pairs[0]["reason"] is None


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"calibration": "C2"}, "calibration or lens changed"),
        ({"lens_position": 6.10}, "calibration or lens changed"),
        ({"flags": ["lens check"]}, "flagged"),
        ({"status": "no tags found"}, "not read"),
        ({"status": "no calibration"}, "not read"),
    ],
)
def test_the_second_photo_breaking_a_rule_disturbs_the_pair(changes, reason):
    pairs = analysis.pairs([photo(0), photo(1, **changes)], breaks=[], camera_events=[])
    assert pairs[0]["reason"] == reason


def test_photos_two_intervals_apart_are_a_pair_and_further_apart_are_not():
    two = analysis.pairs([photo(0), photo(2)], breaks=[], camera_events=[])
    three = analysis.pairs([photo(0), photo(3)], breaks=[], camera_events=[])
    assert (two[0]["reason"], three[0]["reason"]) == (None, "photos missed")


def test_an_app_start_between_the_photos_disturbs_the_pair():
    # The app had been up 50 s at the second photo, taken 60 s after the first.
    pairs = analysis.pairs([photo(0), photo(1, app_up_s=50.0)], breaks=[], camera_events=[])
    assert pairs[0]["reason"] == "app restarted"


def test_a_camera_event_between_the_photos_disturbs_the_pair():
    between, before = T0 + timedelta(seconds=20), T0 - timedelta(seconds=20)
    disturbed = analysis.pairs([photo(0), photo(1)], breaks=[], camera_events=[between])
    undisturbed = analysis.pairs([photo(0), photo(1)], breaks=[], camera_events=[before])
    assert (disturbed[0]["reason"], undisturbed[0]["reason"]) == ("camera event", None)


@pytest.mark.parametrize(
    "utc, day, window",
    [
        # Summer time to 25 October, UTC+2: 07:29 UTC is 09:29 chamber time, before the window.
        (datetime(2026, 10, 24, 7, 29, tzinfo=UTC), "2026-10-24", "nothing moved"),
        (datetime(2026, 10, 24, 7, 30, tzinfo=UTC), "2026-10-24", "trays may move"),
        (datetime(2026, 10, 24, 14, 59, tzinfo=UTC), "2026-10-24", "trays may move"),
        (datetime(2026, 10, 24, 15, 0, tzinfo=UTC), "2026-10-24", "nothing moved"),
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), "2026-10-25", "nothing moved"),
        # From 25 October, UTC+1: 08:00 UTC is 09:00 chamber time, 08:30 UTC is 09:30.
        (datetime(2026, 10, 26, 8, 0, tzinfo=UTC), "2026-10-26", "nothing moved"),
        (datetime(2026, 10, 26, 8, 30, tzinfo=UTC), "2026-10-26", "trays may move"),
    ],
)
def test_each_photo_falls_in_one_chamber_day_and_one_movement_window(utc, day, window):
    assert analysis.window(utc) == (day, window)


def test_steadiness_is_the_rms_and_largest_centre_change_over_undisturbed_pairs():
    photos = [photo(0), photo(1), photo(2), photo(3, flags=["lens check"])]
    centres = {0: {8: (0.0, 0.0)}, 1: {8: (3.0, 4.0)}, 2: {8: (3.0, 4.0)}, 3: {8: (300.0, 400.0)}}
    pairs = analysis.pairs(photos, breaks=[], camera_events=[])
    # 0.1 mm per pixel: changes of 5 px (0.5 mm) and 0; the flagged photo's pair is left out.
    # rms = sqrt((0.5^2 + 0^2) / 2) = 0.3536 mm.
    rows = analysis.steadiness(photos, pairs, centres, mm_per_px=lambda x, y: 0.1)
    assert rows == [
        {"tray": 8, "window": "nothing moved", "pairs": 2, "rms_mm": pytest.approx(0.35355, abs=1e-4),
         "max_mm": pytest.approx(0.5)},
    ]


def test_detection_counts_each_tray_over_lit_photos_and_lists_single_misses():
    photos = [photo(0), photo(1), photo(2, status="no tags found")]
    found = {0: {1, 2}, 1: {1}}
    result = analysis.detection(photos, found, trays=[1, 2])
    day = "2026-10-22"
    assert result["trays"] == [
        {"tray": 1, "day": day, "window": "nothing moved", "photos": 2, "found": 2, "share": 1.0},
        {"tray": 2, "day": day, "window": "nothing moved", "photos": 2, "found": 1, "share": 0.5},
    ]
    assert result["not read"] == [{"day": day, "window": "nothing moved", "status": "no tags found", "photos": 1}]
    assert result["misses"] == [{"capture_id": 1, "taken_at": T0 + timedelta(minutes=1), "missing": [2]}]


def test_tracking_compares_each_read_photo_after_a_shuffle_with_its_map():
    map_a = {"North 1": {"tray": 1, "a1": "SW"}, "South 1": {"tray": 2, "a1": "NE"}}
    map_b = {"South 1": {"tray": 1, "a1": "SW"}, "North 1": {"tray": 2, "a1": "SW"}}
    minute = timedelta(minutes=1)
    shuffles = [
        {"shuffle": "0", "slots": map_a, "start": None, "finish": T0 - minute},
        {"shuffle": "1", "slots": map_b, "start": T0 + 1.5 * minute, "finish": T0 + 2.5 * minute},
    ]
    photos = [photo(0), photo(1), photo(2), photo(3), photo(4, status="no tags found")]
    readings = {
        0: {1: ("North 1", "SW"), 2: ("South 1", "NE")},
        1: {1: ("North 1", "SW")},
        2: {1: ("South 1", "SW")},  # during shuffle 1: belongs to no layout
        3: {1: ("South 1", "SW"), 2: ("North 1", "NE")},
    }
    result = analysis.tracking(photos, readings, shuffles)
    assert result["shuffles"] == [
        {"shuffle": "0", "photos": 2, "right": 3, "wrong": 0, "not found": 1, "not read": 0},
        {"shuffle": "1", "photos": 1, "right": 1, "wrong": 1, "not found": 0, "not read": 1},
    ]
    assert result["wrong"] == [
        {"shuffle": "1", "capture_id": 3, "taken_at": T0 + 3 * minute, "tray": 2,
         "read": ("North 1", "NE"), "map": ("North 1", "SW")},
    ]
