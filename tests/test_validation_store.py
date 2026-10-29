import pytest

from npec_rig import validation_store as store
from npec_rig.calibration import ScaleField
from npec_rig.certainty_map import build_slot_layout, group_sheets, round_errors_by_slot, slot_layout_to_dict
from tests.helpers import sheet_detections, tray_layout_detections

pytestmark = pytest.mark.unit

SLOTS = [{"name": "North 1", "centre": [0, 0], "box": [0, 0, 1, 1]}]


@pytest.fixture(autouse=True)
def isolated_calibration_dir(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("NPEC_RIG_CALIBRATION_DIR", str(tmp_path / "calibration"))


def _counted_round(errors: list[float]) -> dict:
    return {"counted": True, "slot_errors": {"North 1": errors}, "centres": []}


def _timed_round(minute: float) -> dict:
    return _counted_round([1.0] * 10) | {"captured_at": f"2026-10-07T10:{int(minute):02d}:{int(minute % 1 * 60):02d}+00:00"}


def test_rounds_spread_over_less_than_20_minutes_are_validated_but_say_so() -> None:
    # Aaron, 2026-10-07: a 19-minute cycle in the readings (run 3j); shorter spreads are not
    # blocked, the result records and shows it.
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_timed_round(0), _timed_round(1), _timed_round(1.5)]
    store.refresh_results(session)
    assert session["round_span_minutes"] == pytest.approx(1.5)
    assert session["short_span"] is True
    status = store.status(session)
    assert status["state"] == "validated"
    assert ", rounds spread over 1.5 min, under the recommended 20" in status["label"]


def test_rounds_spread_over_20_minutes_or_more_carry_no_note() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_timed_round(0), _timed_round(30), _timed_round(21)]  # first to last: 30 min
    store.refresh_results(session)
    assert session["round_span_minutes"] == pytest.approx(30)
    assert session["short_span"] is False
    assert "spread" not in store.status(session)["label"]


def test_two_rounds_closer_than_6_minutes_are_flagged_even_over_20_minutes() -> None:
    # Aaron, 2026-10-07: rounds at 0, 19 and 20 minutes span 20 but sample about 2 points of the
    # cycle.
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_timed_round(0), _timed_round(19), _timed_round(20)]
    store.refresh_results(session)
    assert session["shortest_gap_minutes"] == pytest.approx(1)
    assert session["short_gap"] is True and session["short_span"] is False
    assert session["judged_with"] == {"min_span_minutes": 20.0, "min_round_gap_minutes": 10.0}
    assert store.status(session)["label"].endswith(", rounds 1.0 min apart, under the recommended 10")


def test_rounds_10_minutes_apart_or_more_carry_no_gap_note() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_timed_round(0), _timed_round(10), _timed_round(20)]
    store.refresh_results(session)
    assert session["shortest_gap_minutes"] == pytest.approx(10)
    assert session["short_gap"] is False
    assert "apart" not in store.status(session)["label"]


def test_times_just_under_a_limit_never_read_as_the_limit() -> None:
    # Code review 2026-10-07: 9.96 printed as "10.0 min apart, under the recommended 10".
    assert store.span_text(9.96) == "9.9"
    assert store.span_text(19.6) == "19"
    assert store.span_text(1.5) == "1.5"


def test_the_span_counts_only_counted_rounds_and_tolerates_missing_times() -> None:
    session = store.new_session("a", SLOTS, [])
    held = _timed_round(40) | {"counted": False}
    session["rounds"] = [_timed_round(0), held, _timed_round(5), _counted_round([1.0] * 10)]
    assert store.round_span_minutes(session) == pytest.approx(5)
    session["rounds"] = [_counted_round([1.0] * 10)] * 3  # no capture times at all
    assert store.round_span_minutes(session) is None
    assert store.short_span(session) is False


def test_a_new_session_round_trips_through_disk() -> None:
    session = store.new_session("20260929T143405685796", SLOTS, [(1.0, 2.0)])
    loaded = store.load_session(session["id"])
    assert loaded == session
    assert loaded["completed_at"] is None
    assert loaded["calibration_centres"] == [[1.0, 2.0]]


def test_session_ids_are_checked_before_any_path_is_built() -> None:
    for bad in ("../../etc/passwd", "20260929", "20260929T1434056857960"):
        with pytest.raises(store.SessionNotFoundError):
            store.load_session(bad)


def test_list_is_newest_first_and_delete_removes_one() -> None:
    first = store.new_session("a", SLOTS, [])
    second = store.new_session("a", SLOTS, [])
    assert [s["id"] for s in store.list_sessions()] == [second["id"], first["id"]]
    store.delete_session(first["id"])
    assert [s["id"] for s in store.list_sessions()] == [second["id"]]
    with pytest.raises(store.SessionNotFoundError):
        store.delete_session(first["id"])


def test_deleting_a_calibration_removes_only_its_sessions() -> None:
    store.new_session("old", SLOTS, [])
    store.new_session("old", SLOTS, [])
    keep = store.new_session("new", SLOTS, [])
    assert store.delete_sessions_for_calibration("old") == 2
    assert [s["id"] for s in store.list_sessions()] == [keep["id"]]


def test_results_pool_counted_rounds_only_and_complete_at_three() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_counted_round([1.0] * 10), _counted_round([-2.0] * 10)]
    session["rounds"].append({"counted": False, "slot_errors": {"North 1": [50.0] * 10}, "centres": []})
    store.refresh_results(session)
    assert session["results"][0]["n"] == 20
    assert session["results"][0]["p95_abs_pct"] == pytest.approx(2.0)
    assert session["completed_at"] is None

    session["rounds"].append(_counted_round([0.5] * 10))
    store.refresh_results(session)
    completed = session["completed_at"]
    assert completed is not None

    session["rounds"].append(_counted_round([0.5] * 10))
    store.refresh_results(session)
    assert session["completed_at"] == completed  # the date it was first completed, kept


def test_each_round_keeps_its_own_figures() -> None:
    round_ = _counted_round([1.0] * 5 + [-3.0] * 5)
    result = store.round_slot_results(round_)["North 1"]
    assert result["n"] == 10
    assert result["median_pct"] == pytest.approx(-1.0)
    assert store.round_slot_results({"counted": False, "slot_errors": None}) is None


def test_median_range_needs_two_counted_rounds() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_counted_round([0.5] * 10)]
    assert store.median_ranges(session) == {"North 1": None}
    session["rounds"] += [
        _counted_round([-1.5] * 10),
        {"counted": False, "slot_errors": {"North 1": [9.0] * 10}, "centres": []},
    ]
    assert store.median_ranges(session)["North 1"] == pytest.approx(2.0)


def test_validated_only_while_no_slot_median_moves_past_the_limit() -> None:
    two_slots = SLOTS + [{"name": "South 1", "centre": [5, 5], "box": [5, 5, 6, 6]}]
    session = store.new_session("a", two_slots, [])

    def round_(north: float, south: float) -> dict:
        errors = {"North 1": [north] * 10, "South 1": [south] * 10}
        return {"counted": True, "slot_errors": errors, "centres": []}

    session["rounds"] = [round_(0.0, 0.0), round_(0.5, -0.5), round_(-0.5, 0.5)]
    store.refresh_results(session)
    assert store.inconsistent_slots(session) == []
    assert store.is_validated(session)

    # A 4th round with a mis-scaled sheet on South 1 takes the status away; completed_at stays.
    session["rounds"].append(round_(0.0, -7.8))
    store.refresh_results(session)
    assert session["completed_at"] is not None
    assert store.inconsistent_slots(session) == ["South 1"]
    assert not store.is_validated(session)


def test_a_drift_shows_before_the_session_is_complete() -> None:
    session = store.new_session("a", SLOTS, [])
    session["rounds"] = [_counted_round([0.0] * 10), _counted_round([-7.8] * 10)]
    assert store.inconsistent_slots(session) == ["North 1"]
    assert not store.is_validated(session)


def test_a_session_saved_before_end_validation_existed_reads_as_ended() -> None:
    session = store.new_session("a", SLOTS, [])
    assert not store.is_ended(session)
    legacy = {k: v for k, v in session.items() if k != "ended_at"}
    assert store.is_ended(legacy)


# Slot order in tray_layout_detections: North 1..6 then South 1..6, 30 tags per sheet.
_SLOT_NAMES = [f"{row} {i}" for row in ("North", "South") for i in range(1, 7)]
_FIELD = ScaleField((1.0, 0.0, 0.0), 4.0, 0.0)  # uniform 4 px/mm: a 30 mm tag is 120 px
_TAG_MM = 30.0


def _tray_session(bad_slot_per_round: list[str | None], round_scale: list[float] | None = None) -> dict:
    """A session whose rounds come from synthetic tray detections: in round i the sheet on
    `bad_slot_per_round[i]` (if any) is a 96% print, and `round_scale[i]` scales every tag of the
    round, as the camera or table moving would."""
    layout = build_slot_layout(group_sheets(tray_layout_detections(), _FIELD, _TAG_MM))
    session = store.new_session("a", slot_layout_to_dict(layout), [])
    for i, bad in enumerate(bad_slot_per_round):
        scale = round_scale[i] if round_scale else 1.0
        capture = tray_layout_detections(side_px=120.0 * scale)
        if bad is not None:
            k = _SLOT_NAMES.index(bad)
            x0, y0 = 800.0 + (k % 6) * 1300.0, (1000.0, 3500.0)[k // 6]
            capture[k * 30 : (k + 1) * 30] = sheet_detections(325, x0, y0, side_px=120.0 * 0.96 * scale)
        errors = round_errors_by_slot(capture, layout, _FIELD, _TAG_MM)
        session["rounds"].append({"counted": True, "slot_errors": errors, "centres": []})
    store.refresh_results(session)
    return session


def test_a_mis_scaled_sheet_moving_between_slots_is_named_each_round() -> None:
    session = _tray_session(["North 2", "South 5", "North 5"])
    assert store.inconsistent_slots(session) == ["North 2", "North 5", "South 5"]
    problems = store.round_problems(session)
    # Only the round the bad sheet sat there: the good sheets on those slots are not named.
    assert [(p["round"], p["slot"]) for p in problems] == [(1, "North 2"), (2, "South 5"), (3, "North 5")]
    assert all(p["offset_pct"] == pytest.approx(-7.84) for p in problems)
    assert not store.is_validated(session)


def test_a_mis_scaled_sheet_that_never_moves_is_flagged_against_the_other_slots() -> None:
    # Nothing moves between rounds, so the round-to-round check sees nothing; the steady reading
    # sits 7.84 points off the other slots, which is what flags it (case (c), 2026-10-01).
    session = _tray_session(["North 2", "North 2", "North 2"])
    assert store.inconsistent_slots(session) == []
    assert store.round_problems(session) == []
    problems = store.offset_problems(session)
    assert [p["slot"] for p in problems] == ["North 2"]
    assert problems[0]["offset_pct"] == pytest.approx(-7.84)
    assert store.flagged_slots(session) == ["North 2"]
    assert not store.is_validated(session)


def test_a_sheet_that_moves_through_one_round_is_not_also_a_steady_offset() -> None:
    session = _tray_session(["North 2", "South 5", "North 5"])
    assert store.offset_problems(session) == []


def test_every_slot_reading_off_since_the_calibration_is_one_table_problem() -> None:
    # Every round 3.96% small in area (0.98 linear): the camera or table moved after calibrating.
    session = _tray_session([None, None, None], round_scale=[0.98, 0.98, 0.98])
    assert store.inconsistent_slots(session) == []
    problems = store.offset_problems(session)
    assert [p["slot"] for p in problems] == [None]  # not 12 slot problems as well
    assert problems[0]["offset_pct"] == pytest.approx(-3.96)
    assert not store.is_validated(session)


def test_a_clean_session_has_no_offsets_and_is_validated() -> None:
    session = _tray_session([None, None, None])
    assert store.offset_problems(session) == []
    assert store.is_validated(session)


def test_two_rounds_are_not_consistent_but_name_no_sheet() -> None:
    session = _tray_session(["North 2", None])
    assert store.inconsistent_slots(session) == ["North 2"]
    assert store.round_problems(session) == []


def test_a_whole_round_shift_is_one_problem_not_twelve() -> None:
    # Every tag of round 2 reads 3.96% small in area (0.98 linear): the camera or table moved.
    session = _tray_session([None, None, None], round_scale=[1.0, 0.98, 1.0])
    assert store.inconsistent_slots(session) == _SLOT_NAMES
    problems = store.round_problems(session)
    assert [(p["round"], p["slot"]) for p in problems] == [(2, None)]
    assert problems[0]["offset_pct"] == pytest.approx(-3.96)


def test_rounds_are_numbered_as_the_page_counts_them_and_only_counted_ones_judged() -> None:
    session = _tray_session([None, "South 1", None, None])
    session["rounds"].insert(0, {"counted": False, "slot_errors": None, "centres": []})
    problems = store.round_problems(session)
    assert [(p["round"], p["slot"]) for p in problems] == [(3, "South 1")]
