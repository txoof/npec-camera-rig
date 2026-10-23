"""Tests for chamber_times.py: the shuffle and event times written in chamber time, turned into
UTC. Expected values are worked by hand: UTC+2 to 25 October 2026 03:00, UTC+1 after.

    cd experiments/round2-run && PYTHONPATH=../../src python -m pytest test_chamber_times.py
"""

from datetime import UTC, datetime

import pytest

import chamber_times

pytestmark = pytest.mark.unit

MAPS = {0, 1, 2, 3}


def row(kind="shuffle", map="1", date="2026-10-23", start="10:05", finish="10:25", note=""):
    return {"kind": kind, "map": map, "date": date, "start": start, "finish": finish, "note": note}


def test_a_shuffle_in_summer_time_is_two_hours_behind_in_utc():
    assert chamber_times.to_utc(row(), MAPS) == {
        "kind": "shuffle", "map": "1", "start_utc": datetime(2026, 10, 23, 8, 5, tzinfo=UTC),
        "finish_utc": datetime(2026, 10, 23, 8, 25, tzinfo=UTC), "note": "",
    }


def test_from_25_october_chamber_time_is_one_hour_ahead_of_utc():
    converted = chamber_times.to_utc(row(date="2026-10-26"), MAPS)
    assert (converted["start_utc"], converted["finish_utc"]) == (
        datetime(2026, 10, 26, 9, 5, tzinfo=UTC), datetime(2026, 10, 26, 9, 25, tzinfo=UTC))


@pytest.mark.parametrize(
    "changes, words",
    [
        ({"start": "10:25", "finish": "10:05"}, "finish before start"),
        ({"start": "09:20"}, "outside the shuffling window"),
        ({"finish": "17:05", "start": "16:50"}, "outside the shuffling window"),
        # 17:00 already belongs to "nothing moved" (analysis.window), so a shuffle ends before it.
        ({"finish": "17:00", "start": "16:50"}, "outside the shuffling window"),
        ({"map": "9"}, "no map 9"),
        ({"start": ""}, "no start"),
        ({"kind": "swap"}, "kind"),
    ],
)
def test_a_row_that_cannot_be_right_stops_with_the_row_named(changes, words):
    with pytest.raises(ValueError, match=words) as raised:
        chamber_times.to_utc(row(**changes), MAPS)
    assert "2026-10-23" in str(raised.value)


def test_a_file_gives_the_shuffles_and_events_in_utc_in_order():
    rows = [
        row(map="0", start="", finish="10:40"),
        row(map="1", date="2026-10-26", start="10:05", finish="10:25"),
        row(kind="event", map="", date="2026-10-26", start="13:00", finish="", note="door opened"),
    ]
    shuffles, events = chamber_times.convert(rows, MAPS)
    assert [(s["map"], s["start_utc"], s["finish_utc"]) for s in shuffles] == [
        ("0", None, datetime(2026, 10, 23, 8, 40, tzinfo=UTC)),
        ("1", datetime(2026, 10, 26, 9, 5, tzinfo=UTC), datetime(2026, 10, 26, 9, 25, tzinfo=UTC)),
    ]
    assert events == [{"time_utc": datetime(2026, 10, 26, 12, 0, tzinfo=UTC), "event": "door opened"}]


@pytest.mark.parametrize(
    "rows, words",
    [
        ([row(map="1", date="2026-10-26"), row(map="2", date="2026-10-23")], "out of order"),
        ([row(map="1"), row(map="1", date="2026-10-26")], "map 1 used twice"),
        ([row(map="1", start="10:05", finish="10:25"), row(map="2", start="10:20", finish="10:40")], "overlaps"),
    ],
)
def test_a_file_that_cannot_be_right_stops_with_the_rows_named(rows, words):
    with pytest.raises(ValueError, match=words):
        chamber_times.convert(rows, MAPS)


@pytest.mark.parametrize("clock", ["02:30", "02:00"])
def test_a_time_in_the_repeated_hour_of_the_clock_change_is_refused(clock):
    # 25 October 2026: 02:00 to 03:00 chamber time happens twice (03:00 summer time becomes 02:00).
    with pytest.raises(ValueError, match="happened twice"):
        chamber_times.to_utc(row(kind="event", map="", date="2026-10-25", start=clock, finish=""), MAPS)


def test_a_map_name_that_is_not_a_number_is_refused_with_the_row_named():
    with pytest.raises(ValueError, match="no map 20b") as raised:
        chamber_times.to_utc(row(map="20b"), MAPS)
    assert "2026-10-23" in str(raised.value)
