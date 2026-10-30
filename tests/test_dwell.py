"""Time each tray spends in each area of the chamber table, and a warning when it stays too long
(#332). Decisions: Aaron, 2026-10-30 (issue #332)."""

from datetime import datetime, timedelta

import pytest

from npec_rig import dwell
from npec_rig.calibration import build_table_frame
from npec_rig.tripwire import CornerBaseline

pytestmark = pytest.mark.unit

PHOTO = (9000, 6000)


def _square(cx: float, cy: float, side: float = 40) -> tuple[tuple[float, float], ...]:
    h = side / 2
    return ((cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h), (cx - h, cy + h))


def _frame(north_y: float, south_y: float, west_x: float = 1000, east_x: float = 8000):
    """The table frame of four corner tags lying square to the photo: the north row at `north_y`,
    the south row at `south_y`."""
    centres = {450: (west_x, north_y), 451: (east_x, north_y), 452: (east_x, south_y), 453: (west_x, south_y)}
    return build_table_frame(CornerBaseline(corners_by_id={i: _square(*c) for i, c in centres.items()}))


@pytest.mark.parametrize(
    ("centre", "area"),
    [
        # North row tags at y 1000, south row at y 5800: the rows meet halfway, at y 3400, not at
        # the photo's own half height (3000). Columns: thirds of the 9000 px photo width, at x
        # 3000 and 6000, not thirds between the tags (x 3333 and 5667).
        ((100, 100), "NW"), ((2990, 3390), "NW"), ((3010, 3390), "NM"), ((5990, 3390), "NM"),
        ((6010, 3390), "NE"), ((8900, 100), "NE"),
        ((2990, 3410), "SW"), ((3010, 3410), "SM"), ((5990, 5900), "SM"), ((6010, 3410), "SE"),
        ((8900, 5900), "SE"),
    ],
)
def test_a_trays_centre_decides_its_area_on_a_3_by_2_grid_between_the_tag_rows_over_the_photo_width(
    centre, area
) -> None:
    assert dwell.area_of(centre, PHOTO, _frame(north_y=1000, south_y=5800)) == area


def test_rows_follow_the_tag_rows_when_the_table_lies_turned_in_the_photo() -> None:
    """The east tags 400 px lower than the west ones: halfway between the rows runs from (1000,
    3400) to (8000, 3800), so through (4500, 3600)."""
    centres = {450: (1000, 1000), 451: (8000, 1400), 452: (8000, 6200), 453: (1000, 5800)}
    frame = build_table_frame(CornerBaseline(corners_by_id={i: _square(*c) for i, c in centres.items()}))

    assert [dwell.area_of(c, PHOTO, frame) for c in ((4500, 3590), (4500, 3610))] == ["NM", "SM"]


@pytest.mark.parametrize(
    ("centre", "area"),
    [((2990, 2990), "NW"), ((3010, 2990), "NM"), ((6010, 2990), "NE"), ((2990, 3010), "SW"), ((5990, 3010), "SM"),
     ((6010, 3010), "SE")],
)
def test_without_a_table_frame_the_photo_itself_is_divided_into_halves_and_thirds(centre, area) -> None:
    assert dwell.area_of(centre, PHOTO, None) == area


# --- Stays ---------------------------------------------------------------------------------------


def _t(text: str) -> datetime:
    return datetime.fromisoformat(f"2027-{text}+00:00")


def test_a_tray_off_the_table_for_part_of_a_day_and_back_in_its_area_stays_there_4_days() -> None:
    """Aaron's example: in NW from 1 January, off the table on 2 January, back in NW the same day
    and there until 5 January counts as 4 days. Off the table, the tray is not found: no reading."""
    readings = [(_t("01-01T00:00"), "NW"), (_t("01-02T08:00"), "NW"), (_t("01-02T15:00"), "NW"),
                (_t("01-04T00:00"), "NW"), (_t("01-05T00:00"), "NW")]

    assert dwell.stays(readings) == [dwell.Stay("NW", _t("01-01T00:00"), _t("01-05T00:00"))]
    assert dwell.stays(readings)[0].end - dwell.stays(readings)[0].start == timedelta(days=4)


def test_a_tray_moved_away_for_days_and_back_starts_a_new_stay_when_it_comes_back() -> None:
    """Aaron's example: in NW 1 January, SW 3 January, NW again 5 January: the run in NW is
    restarted on 5 January."""
    readings = [(_t("01-01T00:00"), "NW"), (_t("01-02T00:00"), "NW"), (_t("01-03T00:00"), "SW"),
                (_t("01-03T12:00"), "SW"), (_t("01-05T00:00"), "NW"), (_t("01-05T06:00"), "NW")]

    assert dwell.stays(readings) == [
        dwell.Stay("NW", _t("01-01T00:00"), _t("01-02T00:00")),
        dwell.Stay("SW", _t("01-03T00:00"), _t("01-03T12:00")),
        dwell.Stay("NW", _t("01-05T00:00"), _t("01-05T06:00")),
    ]


def test_a_tray_beside_its_area_for_3_minutes_has_not_moved() -> None:
    """Tray 1 beside its slot for 3 minutes on 28 October (issue #332): a nudge, not a move."""
    readings = [(_t("01-01T10:00"), "NW"), (_t("01-01T10:01"), "NM"), (_t("01-01T10:02"), "NM"),
                (_t("01-01T10:03"), "NM"), (_t("01-01T10:04"), "NW")]

    assert dwell.stays(readings) == [dwell.Stay("NW", _t("01-01T10:00"), _t("01-01T10:04"))]


@pytest.mark.parametrize(("last_away", "moved"), [("10:59", False), ("11:00", True)])
def test_a_tray_counts_as_moved_after_1_hour_found_in_another_area(last_away, moved) -> None:
    readings = [(_t("01-01T09:00"), "SE"), (_t("01-01T10:00"), "SM"), (_t(f"01-01T{last_away}"), "SM"),
                (_t("01-01T11:30"), "SE")]

    expected = (
        [dwell.Stay("SE", _t("01-01T09:00"), _t("01-01T09:00")), dwell.Stay("SM", _t("01-01T10:00"), _t("01-01T11:00"))]
        if moved else [dwell.Stay("SE", _t("01-01T09:00"), _t("01-01T11:30"))]
    )
    # Moved: back in SE at 11:30 for one photo only is not yet a move back.
    assert dwell.stays(readings) == expected


def test_an_hour_away_spread_over_two_other_areas_is_not_a_move() -> None:
    """NM from 10:10 to 11:15 is over an hour, but not in a row: NE at 10:30 lies between."""
    readings = [(_t("01-01T10:00"), "NW"), (_t("01-01T10:10"), "NM"), (_t("01-01T10:30"), "NE"),
                (_t("01-01T11:15"), "NM"), (_t("01-01T11:20"), "NW")]

    assert dwell.stays(readings) == [dwell.Stay("NW", _t("01-01T10:00"), _t("01-01T11:20"))]
