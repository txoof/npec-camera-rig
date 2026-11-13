"""Time each tray spends in each table location of the chamber, and a warning when it stays too long
(#332). Decisions: Aaron, 2026-10-30 (issue #332)."""

from datetime import datetime, timedelta

import pytest

from npec_rig import database, dwell
from npec_rig.calibration import build_table_frame
from npec_rig.tripwire import CornerBaseline
from tests.helpers import TABLE_STEM, table_calibration, table_photo

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
    ("centre", "location"),
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
def test_a_trays_centre_decides_its_location_on_a_3_by_2_grid_between_the_tag_rows_over_the_photo_width(
    centre, location
) -> None:
    assert dwell.location_of(centre, PHOTO, _frame(north_y=1000, south_y=5800)) == location


def test_rows_follow_the_tag_rows_when_the_table_lies_turned_in_the_photo() -> None:
    """The east tags 400 px lower than the west ones: halfway between the rows runs from (1000,
    3400) to (8000, 3800), so through (4500, 3600)."""
    centres = {450: (1000, 1000), 451: (8000, 1400), 452: (8000, 6200), 453: (1000, 5800)}
    frame = build_table_frame(CornerBaseline(corners_by_id={i: _square(*c) for i, c in centres.items()}))

    assert [dwell.location_of(c, PHOTO, frame) for c in ((4500, 3590), (4500, 3610))] == ["NM", "SM"]


@pytest.mark.parametrize(
    ("centre", "location"),
    [((2990, 2990), "NW"), ((3010, 2990), "NM"), ((6010, 2990), "NE"), ((2990, 3010), "SW"), ((5990, 3010), "SM"),
     ((6010, 3010), "SE")],
)
def test_without_a_table_frame_the_photo_itself_is_divided_into_halves_and_thirds(centre, location) -> None:
    assert dwell.location_of(centre, PHOTO, None) == location


# --- Stays ---------------------------------------------------------------------------------------


def _t(text: str) -> datetime:
    return datetime.fromisoformat(f"2027-{text}+00:00")


def test_a_tray_off_the_table_for_part_of_a_day_and_back_in_its_location_stays_there_4_days() -> None:
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


def test_a_tray_beside_its_location_for_3_minutes_has_not_moved() -> None:
    """Tray 1 beside its slot for 3 minutes on 28 October (issue #332): a nudge, not a move."""
    readings = [(_t("01-01T10:00"), "NW"), (_t("01-01T10:01"), "NM"), (_t("01-01T10:02"), "NM"),
                (_t("01-01T10:03"), "NM"), (_t("01-01T10:04"), "NW")]

    assert dwell.stays(readings) == [dwell.Stay("NW", _t("01-01T10:00"), _t("01-01T10:04"))]


@pytest.mark.parametrize(("last_away", "moved"), [("10:59", False), ("11:00", False), ("11:01", True)])
def test_a_tray_counts_as_moved_after_over_1_hour_found_in_another_location(last_away, moved) -> None:
    """Over 1 hour (Aaron, 2026-10-30): exactly 1 hour is not a move."""
    readings = [(_t("01-01T09:00"), "SE"), (_t("01-01T10:00"), "SM"), (_t(f"01-01T{last_away}"), "SM"),
                (_t("01-01T11:30"), "SE")]

    expected = (
        [dwell.Stay("SE", _t("01-01T09:00"), _t("01-01T09:00")), dwell.Stay("SM", _t("01-01T10:00"), _t(f"01-01T{last_away}"))]
        if moved else [dwell.Stay("SE", _t("01-01T09:00"), _t("01-01T11:30"))]
    )
    # Moved: back in SE at 11:30 for one photo only is not yet a move back.
    assert dwell.stays(readings) == expected


def test_a_tray_flipping_between_two_other_locations_moves_to_the_one_it_was_in_most() -> None:
    """Review of #332: a centre on the line between NM and NE never stays an hour in either, but
    it has left NW. Away from 10:10 to 11:11 (61 minutes, over 1 hour): until each next photo, NM
    10 + 20 + 5 = 35 minutes, NE 10 + 10 + 6 = 26 minutes."""
    readings = [(_t("01-01T10:00"), "NW")] + [
        (_t(f"01-01T{when}"), location)
        for when, location in (("10:10", "NM"), ("10:20", "NE"), ("10:30", "NM"), ("10:40", "NM"), ("10:50", "NE"),
                               ("11:00", "NM"), ("11:05", "NE"), ("11:11", "NM"))
    ]

    assert dwell.stays(readings) == [
        dwell.Stay("NW", _t("01-01T10:00"), _t("01-01T10:00")),
        dwell.Stay("NM", _t("01-01T10:10"), _t("01-01T11:11")),
    ]


# --- An experiment's trays -----------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_photos_and_calibration(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_PHOTOS_DIR", str(tmp_path / "rig"))
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _experiment(**settings) -> int:
    table_calibration()
    experiment = database.create_experiment(uuid="u-332", created_at="2027-01-01T00:00:00+00:00")
    database.start_experiment(experiment["id"], now="2027-01-01T00:00:00+00:00", folder="experiments/x")
    if settings:
        database.update_experiment(experiment["id"], **settings)
    return experiment["id"]


def _read(experiment_id: int, when: str, trays: dict[int, str]) -> None:
    table_photo(experiment_id, _t(when), trays)


def test_a_tray_4_days_in_a_row_in_one_location_is_over_the_limit_and_one_less_is_not() -> None:
    """Tray 8, from 1 hour later and missing from the last photo, is 1 hour short. A photo a day:
    never missing over 48 hours."""
    experiment_id = _experiment()
    _read(experiment_id, "01-01T00:00", {7: "NW"})
    for when in ("01-01T01:00", "01-02T12:00", "01-03T12:00", "01-04T23:00"):
        _read(experiment_id, when, {7: "NW", 8: "SE"})
    _read(experiment_id, "01-05T00:00", {7: "NW"})

    assert dwell.over_limit(experiment_id, at=_t("01-05T00:00").isoformat()) == [
        {"tray_id": 7, "location": "NW", "since": _t("01-01T00:00").isoformat(), "hours": 96.0}
    ]
    assert dwell.over_limit(experiment_id, at=_t("01-04T23:30").isoformat()) == []


def test_the_warning_clears_once_the_tray_has_been_in_another_location_for_an_hour() -> None:
    experiment_id = _experiment()
    for when in ("01-01T00:00", "01-03T00:00", "01-05T00:00", "01-05T10:00"):
        _read(experiment_id, when, {7: "NW"})
    for when in ("01-05T10:30", "01-05T11:30", "01-05T11:31"):
        _read(experiment_id, when, {7: "SM"})

    assert [t["tray_id"] for t in dwell.over_limit(experiment_id, at=_t("01-05T11:30").isoformat())] == [7]
    assert dwell.over_limit(experiment_id, at=_t("01-05T11:31").isoformat()) == []


def test_the_experiments_own_limit_is_used() -> None:
    experiment_id = _experiment(dwell_limit_h=24)
    _read(experiment_id, "01-01T00:00", {8: "SW"})
    _read(experiment_id, "01-01T00:01", {7: "NE"})
    _read(experiment_id, "01-02T00:00", {7: "NE", 8: "SW"})

    assert dwell.over_limit(experiment_id, at=_t("01-02T00:00").isoformat()) == [
        {"tray_id": 8, "location": "SW", "since": _t("01-01T00:00").isoformat(), "hours": 24.0}
    ]


def test_each_trays_hours_in_each_location_over_the_experiment() -> None:
    """Tray 7: NW 2 days, then SE 6 hours. Tray 8: 3 minutes in NM is a nudge, counted in SW."""
    experiment_id = _experiment()
    _read(experiment_id, "01-01T00:00", {7: "NW", 8: "SW"})
    _read(experiment_id, "01-03T00:00", {7: "NW", 8: "SW"})
    _read(experiment_id, "01-03T00:01", {7: "SE", 8: "NM"})
    _read(experiment_id, "01-03T00:04", {8: "SW"})
    _read(experiment_id, "01-03T06:01", {7: "SE"})

    zero = dict.fromkeys(["NW", "NM", "NE", "SW", "SM", "SE"], 0.0)
    assert dwell.hours_per_location(experiment_id) == {
        7: {**zero, "NW": 48.0, "SE": 6.0},
        8: {**zero, "SW": 48.0 + 4 / 60},
    }


@pytest.mark.parametrize(
    ("last", "at", "warned"),
    [
        # Missing 3 days (over 48 h) at day 6: taken away, its stay ended at day 3, no warning.
        ("01-04T00:00", "01-07T00:00", []),
        # Missing 1 day (under 48 h) at day 4.5: still counted in NW, 4.5 days since day 0.
        ("01-04T12:00", "01-05T12:00", [{"tray_id": 7, "location": "NW", "since": "2027-01-01T00:00:00+00:00", "hours": 108.0}]),
    ],
)
def test_a_tray_missing_over_48_hours_was_taken_away_and_is_not_warned_for(last, at, warned) -> None:
    """Aaron, 2026-10-30: #331's rule, database.NOT_SEEN_FOR. Limit 4 days, in NW from day 0."""
    experiment_id = _experiment()
    for when in ("01-01T00:00", "01-02T12:00", last):  # never missing over 48 hours before `last`
        _read(experiment_id, when, {7: "NW"})

    assert dwell.over_limit(experiment_id, at=_t(at).isoformat()) == warned


@pytest.mark.parametrize(
    ("at", "warned"),
    [
        # Missing 2.5 days (over 48 h): taken away, though its stay of 5 days was over the limit.
        ("01-08T12:00", []),
        # Missing 1.5 days (under 48 h): still in NW, 6.5 days since day 0.
        ("01-07T12:00", [{"tray_id": 7, "location": "NW", "since": "2027-01-01T00:00:00+00:00", "hours": 156.0}]),
    ],
)
def test_a_tray_over_the_limit_then_missing_over_48_hours_is_no_longer_warned_for(at, warned) -> None:
    """In NW from day 0 (1 January), photos until day 5, none after. Limit 4 days."""
    experiment_id = _experiment()
    for when in ("01-01T00:00", "01-03T00:00", "01-04T12:00", "01-06T00:00"):
        _read(experiment_id, when, {7: "NW"})

    assert dwell.over_limit(experiment_id, at=_t(at).isoformat()) == warned


def test_a_tray_away_over_48_hours_and_back_in_the_same_location_starts_a_new_stay() -> None:
    """Aaron, 2026-10-30: missing over 48 hours (database.NOT_SEEN_FOR) is taken away; it stops
    counting, and back on the table it counts from a new stay. In NW day 0 to day 1, gone 4 days,
    back in NW day 5 for 6 hours. Limit 4 days."""
    experiment_id = _experiment()
    for when in ("01-01T00:00", "01-02T00:00", "01-06T00:00", "01-06T06:00"):
        _read(experiment_id, when, {7: "NW"})

    assert dwell.over_limit(experiment_id, at=_t("01-06T06:00").isoformat()) == []
    assert dwell.hours_per_location(experiment_id)[7]["NW"] == 24.0 + 6.0


def test_a_rebuilt_calibration_is_used_at_once_not_after_a_restart() -> None:
    """Review of #332: a twin rebuilt from TABLE_STEM with its north corner tags at y 400 and its
    south ones at y 700 puts the rows' meeting line at y 550, so a tray at (450, 450), in SM under
    TABLE_STEM (line at y 300), is in NM. Nothing is read again in between."""
    from npec_rig.calibration import CalibrationArtifact, scale_field_from_dict
    from npec_rig.calibration_store import save_calibration

    experiment_id = _experiment()
    _read(experiment_id, "01-01T00:00", {7: "SM"})
    assert [s.location for s in dwell.tray_stays(experiment_id)[7]] == ["SM"]

    corners = {450: (100, 400), 451: (800, 400), 452: (800, 700), 453: (100, 700)}
    save_calibration(
        CalibrationArtifact(
            created_at="2027-01-02T00:00:00+00:00", frame_stem="20270102T000000000000", rebuilt_from=TABLE_STEM,
            scale_field=scale_field_from_dict({"coeffs": [1.0, 0.0, 0.0], "mean_px_per_mm": 1.0, "residual_std_pct": 0.0}),
            corner_baseline=CornerBaseline(corners_by_id={i: _square(*c, side=10) for i, c in corners.items()}),
        ),
        stem="20270102T000000000000",
    )

    assert [s.location for s in dwell.tray_stays(experiment_id)[7]] == ["NM"]


def _read_again(experiment_id: int, when: str, trays: dict[int, str]) -> None:
    """Read the photo taken at `when` again, a day later, finding `trays` (tray ID: location) in it,
    as Reprocess does."""
    from tests.helpers import TABLE_CENTRES

    (photo,) = [c for c in database.captures_for_experiment(experiment_id) if c["taken_at"] == _t(when).isoformat()]
    database.record_tray_readings(photo["id"], read_at=(_t(when) + timedelta(days=1)).isoformat(), status="read", trays=[
        {"tray_id": tray_id, "slot": None, "a1_corner": None, "placement": "placed",
         "centre_px": list(TABLE_CENTRES[location]), "tilt_deg": 0.0, "margin_mm": None, "found": "photo + tag",
         "warnings": [], "outline_px": None}
        for tray_id, location in trays.items()
    ])


def test_a_photo_read_after_the_stays_were_asked_for_is_in_them_next_time() -> None:
    """#416: the stays are not worked out from scratch on each request, and a new photo still counts."""
    experiment_id = _experiment()
    _read(experiment_id, "01-01T00:00", {7: "NW"})
    _read(experiment_id, "01-02T00:00", {7: "NW"})
    assert dwell.tray_stays(experiment_id) == {7: [dwell.Stay("NW", _t("01-01T00:00"), _t("01-02T00:00"))]}

    _read(experiment_id, "01-03T00:00", {7: "NW"})

    assert dwell.tray_stays(experiment_id) == {7: [dwell.Stay("NW", _t("01-01T00:00"), _t("01-03T00:00"))]}


def test_an_old_photo_read_again_with_other_trays_changes_the_stays() -> None:
    """#416: Reprocess reads the 3 January photo again and now finds tray 9 in SE there instead of
    tray 7, so tray 7's stay ends on 2 January and tray 9 has one of its own."""
    experiment_id = _experiment()
    for day in ("01", "02", "03"):
        _read(experiment_id, f"01-{day}T00:00", {7: "NW"})
    assert dwell.tray_stays(experiment_id)[7][-1].end == _t("01-03T00:00")

    _read_again(experiment_id, "01-03T00:00", {9: "SE"})

    assert dwell.tray_stays(experiment_id) == {
        7: [dwell.Stay("NW", _t("01-01T00:00"), _t("01-02T00:00"))],
        9: [dwell.Stay("SE", _t("01-03T00:00"), _t("01-03T00:00"))],
    }
