"""Time each tray spends in each area of the chamber table, and a warning when it stays too long
(#332). Decisions: Aaron, 2026-10-30 (issue #332)."""

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
