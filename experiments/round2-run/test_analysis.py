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
    rows = analysis.steadiness(photos, pairs, centres, mm_per_px=lambda cal, x, y: 0.1)
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
        0: {1: ("North 1", "SW", "placed"), 2: ("South 1", "NE", "placed")},
        1: {1: ("North 1", "SW", "placed")},
        2: {1: ("South 1", "SW", "placed")},  # during shuffle 1: belongs to no layout
        3: {1: ("South 1", "SW", "placed"), 2: ("North 1", "NE", "placed")},
    }
    result = analysis.tracking(photos, readings, shuffles)
    assert result["shuffles"] == [
        {"shuffle": "0", "photos": 2, "right": 3, "wrong": 0, "doubtful": 0, "not found": 1, "not read": 0},
        {"shuffle": "1", "photos": 1, "right": 1, "wrong": 1, "doubtful": 0, "not found": 0, "not read": 1},
    ]
    assert result["wrong"] == [
        {"shuffle": "1", "capture_id": 3, "taken_at": T0 + 3 * minute, "tray": 2,
         "read": ("North 1", "NE"), "map": ("North 1", "SW")},
    ]


def test_a_photo_with_no_app_uptime_known_leaves_its_pair_out_with_that_reason():
    pairs = analysis.pairs([photo(0), photo(1, app_up_s=None)], breaks=[], camera_events=[])
    assert pairs[0]["reason"] == "app uptime unknown"


def test_capture_jitter_around_two_intervals_keeps_the_pair():
    # One photo missed between them, taken 120.4 s apart by the scheduler.
    later = photo(2, taken_at=T0 + timedelta(seconds=120.4))
    assert analysis.pairs([photo(0), later], breaks=[], camera_events=[])[0]["reason"] is None


def test_a_reading_the_app_flagged_counts_as_doubtful_not_right():
    # Both trays read in the slot the map gives, one marked "two trays in one slot" by the app.
    slots = {"North 1": {"tray": 1, "a1": "SW"}, "South 1": {"tray": 2, "a1": "NE"}}
    shuffles = [{"shuffle": "0", "slots": slots, "start": None, "finish": T0}]
    readings = {0: {1: ("North 1", "SW", "two trays in one slot"), 2: ("South 1", "NE", "close call")}}
    result = analysis.tracking([photo(0)], readings, shuffles)
    assert result["shuffles"][0] == {
        "shuffle": "0", "photos": 1, "right": 0, "wrong": 0, "doubtful": 2, "not found": 0, "not read": 0}
    assert [(d["tray"], d["placement"]) for d in result["doubtful"]] == [
        (1, "two trays in one slot"), (2, "close call")]


def test_a_miss_counts_under_the_tray_and_the_slot_it_was_last_read_in():
    minute = timedelta(minutes=1)
    photos = [photo(0), photo(1), photo(2), photo(3), photo(4)]
    readings = {
        0: {1: ("North 2", "SW", "placed"), 2: ("South 1", "NE", "placed")},
        1: {2: ("South 1", "NE", "placed")},                                    # tray 1 missed
        2: {1: ("North 3", "SW", "placed"), 2: ("South 1", "NE", "placed")},    # moved, seen
        3: {2: ("South 1", "NE", "placed")},                                    # tray 1 missed, last in North 3
        4: {1: ("North 3", "SW", "placed")},                                    # tray 2 missed, during a shuffle
    }
    shuffles = [{"shuffle": "1", "slots": {}, "start": T0 + 3.5 * minute, "finish": T0 + 4.5 * minute}]
    result = analysis.misses(photos, readings, shuffles)
    assert [(m["capture_id"], m["tray"], m["slot"], m["during_shuffle"]) for m in result["misses"]] == [
        (1, 1, "North 2", False), (3, 1, "North 3", False), (4, 2, "South 1", True)]
    assert result["by_tray"] == {1: {"outside shuffles": 2, "during shuffles": 0},
                                 2: {"outside shuffles": 0, "during shuffles": 1}}
    assert result["by_slot"] == {"North 2": {"outside shuffles": 1, "during shuffles": 0},
                                 "North 3": {"outside shuffles": 1, "during shuffles": 0},
                                 "South 1": {"outside shuffles": 0, "during shuffles": 1}}


def test_a_tray_missed_before_it_was_ever_read_has_no_slot():
    photos = [photo(0), photo(1)]
    readings = {0: {2: ("South 1", "NE", "placed")}, 1: {1: ("North 2", "SW", "placed"), 2: ("South 1", "NE", "placed")}}
    result = analysis.misses(photos, readings, [], trays=[1, 2])
    assert [(m["tray"], m["slot"]) for m in result["misses"]] == [(1, "not read yet")]


def test_a_tray_read_that_is_not_on_the_map_counts_as_wrong():
    slots = {"North 1": {"tray": 1, "a1": "SW"}}
    shuffles = [{"shuffle": "0", "slots": slots, "start": None, "finish": T0}]
    readings = {0: {1: ("North 1", "SW", "placed"), 29: ("North 3", "NE", "placed")}}
    result = analysis.tracking([photo(0)], readings, shuffles)
    assert (result["shuffles"][0]["right"], result["shuffles"][0]["wrong"]) == (1, 1)
    assert [(w["tray"], w["read"], w["map"]) for w in result["wrong"]] == [(29, ("North 3", "NE"), None)]


def test_a_map_that_names_a_tray_twice_is_refused():
    slots = {"North 1": {"tray": 1, "a1": "SW"}, "North 2": {"tray": 1, "a1": "NE"}}
    with pytest.raises(ValueError, match="tray 1"):
        analysis.tracking([photo(0)], {}, [{"shuffle": "3", "slots": slots, "start": None, "finish": T0}])


def test_steadiness_uses_the_scale_of_the_pair_s_own_calibration():
    photos = [photo(0), photo(1), photo(2, calibration="C2"), photo(3, calibration="C2")]
    centres = {i: {8: (0.0, 10.0 * i)} for i in range(4)}
    pairs = analysis.pairs(photos, breaks=[], camera_events=[])
    # 10 px per step: C1 at 0.1 mm/px gives 1.0 mm, C2 at 0.2 mm/px gives 2.0 mm; the pair across
    # the change of calibration is left out.
    rows = analysis.steadiness(photos, pairs, centres, mm_per_px=lambda cal, x, y: {"C1": 0.1, "C2": 0.2}[cal])
    assert (rows[0]["pairs"], rows[0]["max_mm"]) == (2, pytest.approx(2.0))
    assert rows[0]["rms_mm"] == pytest.approx(((1.0 ** 2 + 2.0 ** 2) / 2) ** 0.5)
